package com.neurovisionassist.phone

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Log
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
    private var commandServer: PhoneCommandServer? = null
    private var appHttpServer: AppHttpServer? = null
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

        piCommunicator = PiCommunicator(
            scope = lifecycleScope,
            onConnectionStatusUpdate = { isConnected, statusText, lastSent, lastResp ->
                updateState {
                    copy(
                        routePlanner = routePlanner.copy(
                            piConnectionStatus = statusText,
                            lastSentMessage = lastSent,
                            lastPiResponse = lastResp,
                        ),
                    )
                }
            },
            onStartNavigationTriggered = {
                startNavigation()
            },
            onSetStartCallback = { startId ->
                updateState {
                    copy(routePlanner = routePlanner.copy(selectedStartNodeId = startId))
                }
            },
            onSetDestinationCallback = { destId ->
                updateState {
                    copy(routePlanner = routePlanner.copy(selectedDestNodeId = destId))
                }
                calculateRoute()
            }
        )

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACTIVITY_RECOGNITION) != PackageManager.PERMISSION_GRANTED) {
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    requestPermissions(arrayOf(Manifest.permission.ACTIVITY_RECOGNITION), 101)
                }
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

        // Start background command server on port 8888 for voice commands and Pi navigation requests
        commandServer = PhoneCommandServer(
            port = 8888,
            onCommandReceived = { command ->
                runOnUiThread { handleVoiceCommand(command) }
            },
            onNavigateRequested = { source, destination ->
                val startId = IndoorMapRepository.resolveLocationId(source)
                val destId = IndoorMapRepository.resolveLocationId(destination)
                val routeResult = IndoorMapRepository.calculateShortestPath(startId, destId)
                if (routeResult != null && routeResult.steps.isNotEmpty()) {
                    runOnUiThread {
                        updateState {
                            copy(
                                selectedTab = 0,
                                routePlanner = routePlanner.copy(
                                    selectedStartNodeId = routeResult.startNode.id,
                                    selectedDestNodeId = routeResult.destinationNode.id,
                                    calculatedRoute = routeResult,
                                    currentStepIndex = 0,
                                    distanceWalkedOnCurrentStep = 0f,
                                    remainingRouteDistanceMeters = routeResult.totalDistanceMeters,
                                    isNavigating = true,
                                )
                            )
                        }
                        tts?.speak("Navigation started from ${routeResult.startNode.name} to ${routeResult.destinationNode.name}.", TextToSpeech.QUEUE_FLUSH, null, "pi-nav")
                    }
                }
                routeResult
            }
        ).apply { start() }

        // Start AppHttpServer on port 8080 bound to 0.0.0.0 for Pi HTTP API (/ping, /navigate)
        appHttpServer = AppHttpServer(
            port = 8080,
            onNavigateRequested = { source, destination ->
                val startId = IndoorMapRepository.resolveLocationId(source)
                val destId = IndoorMapRepository.resolveLocationId(destination)
                val routeResult = IndoorMapRepository.calculateShortestPath(startId, destId)
                val routeId = "route_${System.currentTimeMillis()}"
                if (routeResult != null && routeResult.steps.isNotEmpty()) {
                    runOnUiThread {
                        updateState {
                            copy(
                                selectedTab = 0,
                                isTracking = true,
                                routePlanner = routePlanner.copy(
                                    selectedStartNodeId = routeResult.startNode.id,
                                    selectedDestNodeId = routeResult.destinationNode.id,
                                    calculatedRoute = routeResult,
                                    currentStepIndex = 0,
                                    distanceWalkedOnCurrentStep = 0f,
                                    remainingRouteDistanceMeters = routeResult.totalDistanceMeters,
                                    isNavigating = true,
                                )
                            )
                        }
                        sensorTracker?.start(windowManager.defaultDisplay.rotation)
                        movementDetector.startTest()
                        tts?.speak("Navigation started from ${routeResult.startNode.name} to ${routeResult.destinationNode.name}.", TextToSpeech.QUEUE_FLUSH, null, "app-http-nav")
                    }

                    val currentHost = uiState.value.routePlanner.piHost
                    val currentPort = uiState.value.routePlanner.piPort
                    val firstStep = routeResult.steps.firstOrNull()
                    val routeReadyPayload = NavigationPayload(
                        type = "ROUTE_READY",
                        instruction = firstStep?.instruction ?: "",
                        distanceMeters = firstStep?.distanceMeters ?: 0f,
                        remainingDistanceMeters = routeResult.totalDistanceMeters,
                        stepDistance = firstStep?.distanceMeters ?: 0f,
                        currentStep = 1,
                        totalSteps = routeResult.steps.size,
                        currentNode = routeResult.startNode.name,
                        nextNode = firstStep?.targetNodeName ?: routeResult.destinationNode.name
                    )
                    piCommunicator.sendNavigationEvent(currentHost, currentPort, routeReadyPayload)

                    val navStartedPayload = NavigationPayload(
                        type = "NAVIGATION_STARTED",
                        instruction = "Navigation started: ${routeResult.startNode.name} to ${routeResult.destinationNode.name}",
                        distanceMeters = firstStep?.distanceMeters ?: 0f,
                        remainingDistanceMeters = routeResult.totalDistanceMeters,
                        stepDistance = firstStep?.distanceMeters ?: 0f,
                        currentStep = 1,
                        totalSteps = routeResult.steps.size,
                        currentNode = routeResult.startNode.name,
                        nextNode = firstStep?.targetNodeName ?: routeResult.destinationNode.name
                    )
                    piCommunicator.sendNavigationEvent(currentHost, currentPort, navStartedPayload)
                }
                if (routeResult != null) Pair(routeResult, routeId) else null
            }
        ).apply { start() }

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
        commandServer?.stop()
        commandServer = null
        appHttpServer?.stop()
        appHttpServer = null
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

    private fun handleVoiceCommand(commandText: String) {
        val lower = commandText.lowercase().trim()
        Log.d("MainActivity", "Processing voice command from Pi: '$commandText'")

        when {
            lower.contains("pause") -> pauseNavigation()
            lower.contains("resume") -> resumeNavigation()
            lower.contains("cancel") || lower.contains("stop navigation") -> cancelNavigation()
            else -> {
                // Find destination node in map matching voice command
                val matchedNode = IndoorMapRepository.userLocations.firstOrNull { node ->
                    lower.contains(node.name.lowercase()) || lower.contains(node.id.lowercase())
                } ?: run {
                    val alias = when {
                        lower.contains("206") -> "LH-206"
                        lower.contains("201") -> "LH-201"
                        lower.contains("202") -> "LH-202"
                        lower.contains("203") -> "LH-203"
                        lower.contains("204") -> "LH-204"
                        lower.contains("205") -> "LH-205"
                        lower.contains("207") -> "LH-207"
                        lower.contains("208") -> "L-208"
                        lower.contains("209") -> "L-209"
                        lower.contains("210") -> "L-210"
                        lower.contains("211") -> "L-211"
                        lower.contains("212") -> "L-212"
                        lower.contains("213") -> "L-213"
                        lower.contains("lounge") -> "Student Lounge"
                        lower.contains("library") -> "Library"
                        lower.contains("staff") -> "Staff Room"
                        lower.contains("washroom") || lower.contains("toilet") -> "Washroom"
                        lower.contains("balcony") -> "Balcony"
                        lower.contains("lift") || lower.contains("elevator") -> "Lift"
                        lower.contains("stairs") -> "Stairs"
                        else -> null
                    }
                    alias?.let { name -> IndoorMapRepository.userLocations.firstOrNull { it.name == name } }
                }

                if (matchedNode != null) {
                    updateState {
                        copy(routePlanner = routePlanner.copy(selectedDestNodeId = matchedNode.id))
                    }
                    calculateRoute()
                    startNavigation()
                } else {
                    Log.w("MainActivity", "Could not match destination for voice command: '$commandText'")
                }
            }
        }
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
        val routePlannerState = uiState.value.routePlanner
        val startId = routePlannerState.selectedStartNodeId
        val destId = routePlannerState.selectedDestNodeId

        // Recalculate and validate route from latest selected start and destination
        val route = IndoorMapRepository.calculateShortestPath(startId, destId)
        if (route == null || route.steps.isEmpty() || route.destinationNode.id != destId) {
            Log.e("MainActivity", "startNavigation() aborted: Invalid, unreachable, or stale route from '$startId' to '$destId'.")
            updateState {
                copy(
                    message = "Cannot start navigation: Invalid or unreachable route from $startId to $destId.",
                    routePlanner = routePlanner.copy(isNavigating = false, calculatedRoute = null)
                )
            }
            return
        }

        Log.d("MainActivity", "startNavigation() validated successfully. Start: $startId, Dest: $destId, Route Dest: ${route.destinationNode.name}, Total Dist: ${route.totalDistanceMeters}m")

        updateState {
            copy(
                routePlanner = routePlanner.copy(
                    calculatedRoute = route,
                    isNavigating = true,
                    isPaused = false,
                    currentStepIndex = 0,
                    distanceWalkedOnCurrentStep = 0f,
                    remainingRouteDistanceMeters = route.totalDistanceMeters,
                    expectedHeadingDegrees = route.steps.firstOrNull()?.headingDegrees,
                    offRouteWarning = null,
                ),
            )
        }

        sensorTracker?.start(windowManager.defaultDisplay.rotation)
        movementDetector.startTest()

        val firstStep = route.steps.firstOrNull()
        val firstInstruction = firstStep?.instruction
        val speechText = firstInstruction?.replace("\n", " ") ?: "Starting navigation."

        val payload = NavigationPayload(
            type = "NAVIGATION_STARTED",
            instruction = speechText,
            distanceMeters = firstStep?.distanceMeters ?: 0f,
            remainingDistanceMeters = route.totalDistanceMeters,
            currentNode = route.startNode.name,
            nextNode = firstStep?.targetNodeName ?: route.destinationNode.name,
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
        val currentStep = route?.steps?.getOrNull(uiState.value.routePlanner.currentStepIndex)
        sendEventToPi(
            NavigationPayload(
                type = "NAVIGATION_PAUSED",
                instruction = "Navigation paused.",
                distanceMeters = currentStep?.distanceMeters ?: 0f,
                remainingDistanceMeters = uiState.value.routePlanner.remainingRouteDistanceMeters,
                currentNode = currentStep?.targetNodeName ?: route?.startNode?.name ?: "",
                nextNode = route?.destinationNode?.name ?: "",
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
                distanceMeters = currentStep?.distanceMeters ?: 0f,
                remainingDistanceMeters = uiState.value.routePlanner.remainingRouteDistanceMeters,
                currentNode = currentStep?.targetNodeName ?: route?.startNode?.name ?: "",
                nextNode = route?.destinationNode?.name ?: "",
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
                distanceMeters = 0f,
                remainingDistanceMeters = 0f,
                currentNode = route?.startNode?.name ?: "",
                nextNode = "",
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
            distanceMeters = 0f,
            remainingDistanceMeters = 0f,
            currentNode = "Phone",
            nextNode = "Raspberry Pi",
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
        if (ttsReady) {
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
        movementDetector.startTest()
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
        movementDetector.stopTest()
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
                routePlanner = routePlanner.copy(isNavigating = false, isPaused = false),
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