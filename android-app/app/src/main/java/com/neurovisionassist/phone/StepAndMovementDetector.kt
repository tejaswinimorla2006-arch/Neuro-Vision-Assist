package com.neurovisionassist.phone

import android.util.Log
import kotlin.math.pow
import kotlin.math.sqrt

class StepAndMovementDetector(
    private val onStateUpdate: (TrackingUiState.() -> TrackingUiState) -> Unit,
    private val onStepDetected: ((Float) -> Unit)? = null,
) {
    var isTesting = false
        private set

    private var stepCount = 0
    private var estimatedDistanceMeters = 0f
    private var lastStepLengthMeters = 0f
    private var motionState = "Stopped"
    private var lastStepIntervalMs = 0L

    private var lastStepTimestampNanos = 0L
    private var filteredAccel = 9.81f
    private var prevFilteredAccel = 9.81f
    private var prevPrevFilteredAccel = 9.81f

    private var stepMinAccel = 9.81f
    private var stepMaxAccel = 9.81f

    private val accelWindow = FloatArray(20)
    private var windowIndex = 0
    private var windowFilled = false

    fun startTest() {
        isTesting = true
        resetCounts()
        Log.d(TAG, "Movement test started.")
    }

    fun stopTest() {
        isTesting = false
        motionState = "Stopped"
        updateUi()
        Log.d(TAG, "Movement test stopped. Total steps: $stepCount, Distance: ${"%.2f".format(estimatedDistanceMeters)}m")
    }

    fun resetTest() {
        resetCounts()
        Log.d(TAG, "Movement test reset.")
    }

    private fun resetCounts() {
        stepCount = 0
        estimatedDistanceMeters = 0f
        lastStepLengthMeters = 0f
        lastStepIntervalMs = 0L
        motionState = if (isTesting) "Stationary" else "Stopped"
        lastStepTimestampNanos = 0L
        filteredAccel = 9.81f
        prevFilteredAccel = 9.81f
        prevPrevFilteredAccel = 9.81f
        stepMinAccel = 9.81f
        stepMaxAccel = 9.81f
        windowIndex = 0
        windowFilled = false
        updateUi()
    }

    fun processSensors(
        accel: VectorReading?,
        gyro: VectorReading?,
        heading: Float?,
        timestampNanos: Long,
    ) {
        if (accel == null) return

        val accelMag = sqrt(accel.x * accel.x + accel.y * accel.y + accel.z * accel.z)
        val gyroMag = if (gyro != null) sqrt(gyro.x * gyro.x + gyro.y * gyro.y + gyro.z * gyro.z) else 0f

        // Exponential low-pass filter to smooth out high-frequency noise/shaking
        prevPrevFilteredAccel = prevFilteredAccel
        prevFilteredAccel = filteredAccel
        filteredAccel = ALPHA * filteredAccel + (1f - ALPHA) * accelMag

        // Update sliding window for variance-based stationary detection
        accelWindow[windowIndex] = accelMag
        windowIndex = (windowIndex + 1) % accelWindow.size
        if (windowIndex == 0) windowFilled = true

        val variance = calculateVariance(accelWindow, if (windowFilled) accelWindow.size else windowIndex)
        val isStationary = variance < STATIONARY_VARIANCE_THRESHOLD && gyroMag < STATIONARY_GYRO_THRESHOLD

        if (isStationary) {
            if (motionState != "Stationary") {
                motionState = "Stationary"
                Log.d(TAG, "Motion state changed to: Stationary")
            }
            stepMinAccel = filteredAccel
            stepMaxAccel = filteredAccel
            updateUi()
            return
        } else {
            if (motionState != "Walking") {
                motionState = "Walking"
                Log.d(TAG, "Motion state changed to: Walking")
            }
        }

        // Track local min and max acceleration during step cycle
        if (filteredAccel < stepMinAccel) stepMinAccel = filteredAccel
        if (filteredAccel > stepMaxAccel) stepMaxAccel = filteredAccel

        // Peak detection: local peak in filtered acceleration signal
        val isPeak = prevFilteredAccel > prevPrevFilteredAccel &&
                prevFilteredAccel > filteredAccel &&
                prevFilteredAccel > PEAK_THRESHOLD

        if (isPeak && lastStepTimestampNanos > 0) {
            val intervalNanos = timestampNanos - lastStepTimestampNanos
            val intervalMs = intervalNanos / 1_000_000

            // Debounce / refractory period filtering (300 ms to 2500 ms)
            if (intervalMs in MIN_STEP_INTERVAL_MS..MAX_STEP_INTERVAL_MS) {
                val accelDiff = (stepMaxAccel - stepMinAccel).coerceAtLeast(0.1f)

                // Weinberg dynamic step length estimation: StepLength = K * (a_max - a_min)^(1/4)
                val rawStepLength = WEINBERG_K * accelDiff.toDouble().pow(0.25).toFloat()
                val stepLength = rawStepLength.coerceIn(MIN_STEP_LENGTH, MAX_STEP_LENGTH)

                stepCount++
                estimatedDistanceMeters += stepLength
                lastStepLengthMeters = stepLength
                lastStepIntervalMs = intervalMs
                lastStepTimestampNanos = timestampNanos

                Log.d(
                    TAG,
                    "Step #$stepCount detected | Interval: ${intervalMs}ms | StepLength: ${"%.2f".format(stepLength)}m | " +
                            "TotalDistance: ${"%.2f".format(estimatedDistanceMeters)}m | Heading: ${heading?.let { "%.1f".format(it) } ?: "--"} deg | State: $motionState",
                )

                // Notify navigation waypoint tracker of detected step movement
                onStepDetected?.invoke(stepLength)

                // Reset min/max for next step cycle
                stepMinAccel = filteredAccel
                stepMaxAccel = filteredAccel
                updateUi()
                return
            } else if (intervalMs > MAX_STEP_INTERVAL_MS) {
                lastStepTimestampNanos = timestampNanos
                stepMinAccel = filteredAccel
                stepMaxAccel = filteredAccel
            }
        } else if (isPeak && lastStepTimestampNanos == 0L) {
            lastStepTimestampNanos = timestampNanos
            stepMinAccel = filteredAccel
            stepMaxAccel = filteredAccel
        }

        updateUi()
    }

    private fun calculateVariance(data: FloatArray, size: Int): Float {
        if (size <= 1) return 0f
        var sum = 0f
        for (i in 0 until size) sum += data[i]
        val mean = sum / size
        var varianceSum = 0f
        for (i in 0 until size) {
            val diff = data[i] - mean
            varianceSum += diff * diff
        }
        return varianceSum / size
    }

    private fun updateUi() {
        onStateUpdate {
            copy(
                movementTest = movementTest.copy(
                    isTesting = isTesting,
                    stepCount = stepCount,
                    estimatedDistanceMeters = estimatedDistanceMeters,
                    lastStepLengthMeters = lastStepLengthMeters,
                    motionState = motionState,
                    stepIntervalMs = lastStepIntervalMs,
                ),
            )
        }
    }

    companion object {
        private const val TAG = "MovementTracker"
        private const val ALPHA = 0.75f
        private const val PEAK_THRESHOLD = 10.5f
        private const val MIN_STEP_INTERVAL_MS = 300L
        private const val MAX_STEP_INTERVAL_MS = 2500L
        private const val WEINBERG_K = 0.42f
        private const val MIN_STEP_LENGTH = 0.35f
        private const val MAX_STEP_LENGTH = 1.15f
        private const val STATIONARY_VARIANCE_THRESHOLD = 0.25f
        private const val STATIONARY_GYRO_THRESHOLD = 0.5f
    }
}