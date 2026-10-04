package com.neurovisionassist.phone

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.exceptions.UnavailableApkTooOldException
import com.google.ar.core.exceptions.UnavailableArcoreNotInstalledException
import com.google.ar.core.exceptions.UnavailableDeviceNotCompatibleException
import com.google.ar.core.exceptions.UnavailableException
import com.google.ar.core.exceptions.UnavailableSdkTooOldException
import com.google.ar.core.exceptions.UnavailableUserDeclinedInstallationException
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val uiState = mutableStateOf(TrackingUiState())
    private var arSession: Session? = null
    private var cameraView: GLSurfaceView? = null
    private lateinit var movementDetector: StepAndMovementDetector
    private lateinit var waypointTracker: AutomaticWaypointTracker
    private lateinit var piCommunicator: PiCommunicator
    private var sensorTracker: PhoneSensorTracker? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var pendingSpeech = false
    private var activityResumed = false
    private var userRequestedArInstall = true
    private var arInstallPromptShown = false
    private var isArSupported: Boolean? = null

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            checkArSupport()
        } else {
            startSensorOnlyMode("Camera permission denied. Operating in sensor-only mode.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        piCommunicator = PiCommunicator(lifecycleScope) { isConnected, statusText, lastSent, lastResp ->
            updateState {
                copy(
                    routePlanner = routePlanner.copy(
                        piConnectionStatus = statusText,
                        lastSentMessage = lastSent,
                        lastPiResponse = lastResp,
                    ),
                )
            }
        }

        waypointTracker = AutomaticWaypointTracker(::updateState, ::onLocalSpeakInstruction) { payload ->
            sendEventToPi(payload)
        }

        movementDetector = StepAndMovementDetector(::updateState) { stepLength ->
            waypointTracker.processStep(stepLength, uiState.value)
        }

        sensorTracker = PhoneSensorTracker(this, { transform ->
            val oldHeading = uiState.value.headingDegrees
            updateState(transform)
            val newHeading = uiState.value.headingDegrees
            if (newHeading != null && newHeading != oldHeading) {
                val calHeading = (newHeading + uiState.value.routePlanner.mapHeadingOffsetDegrees + 360f) % 360f
                waypointTracker.checkHeadingAndRoute(calHeading, uiState.value)
            }
        }, movementDetector)

        tts = TextToSpeech(this) { result ->
            ttsReady = result == TextToSpeech.SUCCESS
            if (ttsReady && pendingSpeech) speakTrackingStarted()
        }

        runCatching {
            ArCoreApk.getInstance().checkAvailabilityAsync(this) { availability ->
                if (isFinishing || isDestroyed) return@checkAvailabilityAsync
                val supported = availability.isSupported
                isArSupported = supported
                if (!supported) {
                    updateState {
                        copy(
                            arTrackingState = "Unsupported — Sensor-only mode",
                            message = "ARCore is not supported on this device. App will run in sensor-only mode.",
                        )
                    }
                }
            }
        }

        setContent {
            MainAppContainer(
                state = uiState.value,
                cameraView = cameraView,
                onSelectTab = { tab -> updateState { copy(selectedTab = tab) } },
                onStartTracking = ::startTracking,
                onStopTracking = ::stopTracking,
                onStartMovementTest = ::startMovementTest,
                onStopMovementTest = ::stopMovementTest,
                onResetMovementTest = ::resetMovementTest,
                onSelectStartLocation = { id -> updateState { copy(routePlanner = routePlanner.copy(selectedStartNodeId = id)) } },
                onSelectDestination = { id -> updateState { copy(routePlanner = routePlanner.copy(selectedDestNodeId = id)) } },
                onCalculateRoute = ::calculateRoute,
                onStartNavigation = ::startNavigation,
                onPauseNavigation = ::pauseNavigation,
                onResumeNavigation = ::resumeNavigation,
                onCancelNavigation = ::cancelNavigation,
                onUpdatePiConfig = ::updatePiConfig,
                onTestPiConnection = ::testPiConnection,
            )
        }
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        if (arInstallPromptShown) {
            arInstallPromptShown = false
            createArSession()
            return
        }
        if (uiState.value.isTracking || uiState.value.movementTest.isTesting || uiState.value.routePlanner.isNavigating) {
            val session = arSession
            if (session != null) {
                resumeTracking(session)
            } else {
                sensorTracker?.start(windowManager.defaultDisplay.rotation)
            }
        }
    }

    override fun onPause() {
        activityResumed = false
        cameraView?.onPause()
        sensorTracker?.stop()
        runCatching { arSession?.pause() }
        super.onPause()
    }

    override fun onDestroy() {
        cameraView?.onPause()
        cameraView = null
        sensorTracker?.stop()
        arSession?.close()
        arSession = null
        tts?.stop()
        tts?.shutdown()
        tts = null
        super.onDestroy()
    }

    private fun startTracking() {
        if (uiState.value.isTracking) return

        if (arSession != null) {
            resumeTracking(arSession!!)
            return
        }

        if (isArSupported == false) {
            startSensorOnlyMode("Running in sensor-only mode.")
            return
        }

        updateState {
            copy(status = "Checking camera access", arTrackingState = "Checking", message = null)
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
            return
        }

        checkArSupport()
    }

    private fun startMovementTest() {
        sensorTracker?.start(windowManager.defaultDisplay.rotation)
        movementDetector.startTest()
        updateState {
            copy(
                status = "Movement Test active",
                isTracking = true,
            )
        }
    }

    private fun stopMovementTest() {
        movementDetector.stopTest()
    }

    private fun resetMovementTest() {
        movementDetector.resetTest()
    }

    private fun calculateRoute() {
        val startId = uiState.value.routePlanner.selectedStartNodeId
        val destId = uiState.value.routePlanner.selectedDestNodeId
        val route = IndoorMapRepository.calculateShortestPath(startId, destId)
        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    calculatedRoute = route,
                    isNavigating = false,
                    isPaused = false,
                    currentStepIndex = 0,
                    distanceWalkedOnCurrentStep = 0f,
                    remainingRouteDistanceMeters = route?.totalDistanceMeters ?: 0f,
                    expectedHeadingDegrees = route?.steps?.firstOrNull()?.headingDegrees,
                    offRouteWarning = null,
                ),
            )
        }
    }

    private fun startNavigation() {
        val route = uiState.value.routePlanner.calculatedRoute ?: return
        sensorTracker?.start(windowManager.defaultDisplay.rotation)
        movementDetector.startTest()

        val firstStep = route.steps.firstOrNull()
        val firstInstruction = firstStep?.instruction

        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    isNavigating = true,
                    isPaused = false,
                    currentStepIndex = 0,
                    distanceWalkedOnCurrentStep = 0f,
                    remainingRouteDistanceMeters = route.totalDistanceMeters,
                    expectedHeadingDegrees = firstStep?.headingDegrees,
                    offRouteWarning = null,
                ),
            )
        }

        // Send NAVIGATION_STARTED and first NAVIGATION_INSTRUCTION event to Pi
        val speechText = firstInstruction?.replace("\n", " ") ?: "Starting navigation."
        val payload = NavigationPayload(
            type = "NAVIGATION_STARTED",
            instruction = speechText,
            distanceRemainingMeters = route.totalDistanceMeters,
            currentLocation = route.startNode.name,
            nextLocation = firstStep?.targetNodeName ?: route.destinationNode.name,
            heading = uiState.value.headingDegrees,
            expectedHeading = firstStep?.headingDegrees,
        )
        sendEventToPi(payload)
    }

    private fun pauseNavigation() {
        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    isPaused = true,
                ),
            )
        }
        val route = uiState.value.routePlanner.calculatedRoute
        sendEventToPi(
            NavigationPayload(
                type = "NAVIGATION_PAUSED",
                instruction = "Navigation paused.",
                distanceRemainingMeters = uiState.value.routePlanner.remainingRouteDistanceMeters,
                currentLocation = route?.startNode?.name ?: "",
                nextLocation = route?.destinationNode?.name ?: "",
                heading = uiState.value.headingDegrees,
            ),
        )
    }

    private fun resumeNavigation() {
        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    isPaused = false,
                ),
            )
        }
        val route = uiState.value.routePlanner.calculatedRoute
        val currentStep = route?.steps?.getOrNull(uiState.value.routePlanner.currentStepIndex)
        val instruction = currentStep?.instruction?.replace("\n", " ") ?: "Navigation resumed."

        sendEventToPi(
            NavigationPayload(
                type = "NAVIGATION_RESUMED",
                instruction = instruction,
                distanceRemainingMeters = uiState.value.routePlanner.remainingRouteDistanceMeters,
                currentLocation = currentStep?.targetNodeName ?: route?.startNode?.name ?: "",
                nextLocation = route?.destinationNode?.name ?: "",
                heading = uiState.value.headingDegrees,
            ),
        )
    }

    private fun cancelNavigation() {
        val route = uiState.value.routePlanner.calculatedRoute
        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    isNavigating = false,
                    isPaused = false,
                    currentStepIndex = 0,
                    distanceWalkedOnCurrentStep = 0f,
                    offRouteWarning = null,
                ),
            )
        }
        sendEventToPi(
            NavigationPayload(
                type = "NAVIGATION_CANCELLED",
                instruction = "Navigation cancelled.",
                distanceRemainingMeters = 0f,
                currentLocation = route?.startNode?.name ?: "",
                nextLocation = "",
                heading = uiState.value.headingDegrees,
            ),
        )
    }

    private fun updatePiConfig(host: String, port: Int) {
        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    piHost = host,
                    piPort = port,
                ),
            )
        }
    }

    private fun testPiConnection() {
        val host = uiState.value.routePlanner.piHost
        val port = uiState.value.routePlanner.piPort
        val testPayload = NavigationPayload(
            type = "TEST_CONNECTION",
            instruction = "Testing connection to Raspberry Pi.",
            distanceRemainingMeters = 0f,
            currentLocation = "Phone",
            nextLocation = "Raspberry Pi",
            heading = uiState.value.headingDegrees,
        )
        piCommunicator.sendNavigationEvent(host, port, testPayload)
    }

    private fun sendEventToPi(payload: NavigationPayload) {
        val host = uiState.value.routePlanner.piHost
        val port = uiState.value.routePlanner.piPort
        piCommunicator.sendNavigationEvent(host, port, payload)
    }

    private fun onLocalSpeakInstruction(text: String) {
        // Log instruction locally; primary TTS is handled by Pi
        if (ttsReady) {
            // Optional local feedback when debugging
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "local-nav")
        }
    }

    private fun checkArSupport() {
        updateState { copy(status = "Checking ARCore support", arTrackingState = "Checking", message = null) }
        try {
            ArCoreApk.getInstance().checkAvailabilityAsync(this) { availability ->
                if (isFinishing || isDestroyed) return@checkAvailabilityAsync
                val supported = availability.isSupported
                isArSupported = supported
                if (supported) {
                    createArSession()
                } else {
                    startSensorOnlyMode("This phone is not ARCore-certified.")
                }
            }
        } catch (error: RuntimeException) {
            startSensorOnlyMode("Could not check ARCore support: ${error.message ?: error.javaClass.simpleName}")
        }
    }

    private fun createArSession() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            startSensorOnlyMode("Camera permission denied. Running in sensor-only mode.")
            return
        }

        try {
            when (ArCoreApk.getInstance().requestInstall(this, userRequestedArInstall)) {
                ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                    userRequestedArInstall = false
                    arInstallPromptShown = true
                    updateState {
                        copy(status = "Waiting for Google Play Services for AR", arTrackingState = "Installing", message = null)
                    }
                    return
                }

                ArCoreApk.InstallStatus.INSTALLED -> Unit
            }

            val session = Session(this)
            session.configure(Config(session))
            session.resume()
            arSession = session
            startSensorsAndCamera(session)
        } catch (error: UnavailableException) {
            handleArFailure(arFailureMessage(error))
        } catch (error: SecurityException) {
            handleArFailure("Camera access was denied while starting ARCore.")
        } catch (error: RuntimeException) {
            handleArFailure("Could not start ARCore: ${error.message ?: error.javaClass.simpleName}")
        }
    }

    private fun startSensorsAndCamera(session: Session) {
        try {
            val view = GLSurfaceView(this).apply {
                setEGLContextClientVersion(2)
                preserveEGLContextOnPause = true
                setRenderer(
                    ArCameraRenderer(
                        session = session,
                        onFrame = { trackingState, x, y, z ->
                            runOnUiThread {
                                if (arSession === session && uiState.value.isTracking) {
                                    updateState {
                                        copy(
                                            arTrackingState = trackingState,
                                            poseX = x,
                                            poseY = y,
                                            poseZ = z,
                                        )
                                    }
                                }
                            }
                        },
                        onError = { message -> runOnUiThread { handleArFailure(message) } },
                    ),
                )
                renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
            }
            cameraView = view
            if (activityResumed) view.onResume()
            sensorTracker?.start(windowManager.defaultDisplay.rotation)
            updateState {
                copy(
                    status = "Tracking active",
                    arTrackingState = "Initializing",
                    isTracking = true,
                    poseX = null,
                    poseY = null,
                    poseZ = null,
                    message = null,
                )
            }
            speakTrackingStarted()
        } catch (error: RuntimeException) {
            handleArFailure("Could not initialize the tracking camera: ${error.message ?: error.javaClass.simpleName}")
        }
    }

    private fun resumeTracking(session: Session) {
        try {
            session.resume()
            cameraView?.onResume()
            sensorTracker?.start(windowManager.defaultDisplay.rotation)
            updateState { copy(status = "Tracking active", isTracking = true, message = null) }
        } catch (error: SecurityException) {
            handleArFailure("Camera access is no longer available.")
        } catch (error: RuntimeException) {
            handleArFailure("Could not resume AR tracking: ${error.message ?: error.javaClass.simpleName}")
        }
    }

    private fun startSensorOnlyMode(message: String? = null) {
        sensorTracker?.start(windowManager.defaultDisplay.rotation)
        updateState {
            copy(
                status = "Tracking active",
                arTrackingState = "Unsupported — Sensor-only mode",
                isTracking = true,
                poseX = null,
                poseY = null,
                poseZ = null,
                message = message,
            )
        }
        speakTrackingStarted()
    }

    private fun handleArFailure(reason: String) {
        cameraView?.onPause()
        cameraView = null
        runCatching { arSession?.pause() }
        arSession?.close()
        arSession = null
        startSensorOnlyMode("ARCore unavailable: $reason")
    }

    private fun stopTracking() {
        cameraView?.onPause()
        sensorTracker?.stop()
        runCatching { arSession?.pause() }
        arSession?.close()
        arSession = null
        cameraView = null
        val currentArState = uiState.value.arTrackingState
        updateState {
            copy(
                status = "Stopped",
                arTrackingState = if (currentArState.startsWith("Unsupported")) "Unsupported — Sensor-only mode" else "Not tracking",
                headingDegrees = null,
                accelerometer = null,
                gyroscope = null,
                magnetometer = null,
                poseX = null,
                poseY = null,
                poseZ = null,
                isTracking = false,
                message = null,
            )
        }
    }

    private fun speakTrackingStarted() {
        val engine = tts
        if (!ttsReady || engine == null) {
            pendingSpeech = true
            return
        }
        pendingSpeech = false
        val languageResult = engine.setLanguage(Locale.getDefault())
        if (languageResult == TextToSpeech.LANG_MISSING_DATA || languageResult == TextToSpeech.LANG_NOT_SUPPORTED) {
            updateState { copy(message = "Text-to-Speech does not support the current device language.") }
            return
        }
        engine.speak("Phone navigation tracking started.", TextToSpeech.QUEUE_FLUSH, null, "tracking-started")
    }

    private fun updateState(transform: TrackingUiState.() -> TrackingUiState) {
        uiState.value = uiState.value.transform()
    }

    private fun arFailureMessage(error: UnavailableException): String = when (error) {
        is UnavailableDeviceNotCompatibleException -> "This phone does not support ARCore."
        is UnavailableUserDeclinedInstallationException -> "Google Play Services for AR installation was declined."
        is UnavailableArcoreNotInstalledException -> "Google Play Services for AR is not installed."
        is UnavailableApkTooOldException -> "Update Google Play Services for AR and try again."
        is UnavailableSdkTooOldException -> "Update this app to a newer ARCore SDK."
        else -> "ARCore could not start: ${error.message ?: error.javaClass.simpleName}"
    }
}