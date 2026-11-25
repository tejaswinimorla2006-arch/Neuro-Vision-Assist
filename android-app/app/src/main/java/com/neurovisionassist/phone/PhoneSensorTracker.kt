package com.neurovisionassist.phone

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.view.Surface
import android.util.Log

class PhoneSensorTracker(
    context: Context,
    private val onReadings: (TrackingUiState.() -> TrackingUiState) -> Unit,
    private val movementDetector: StepAndMovementDetector,
) : SensorEventListener {
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val magnetometer = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
    private val gravityValues = FloatArray(3)
    private val magneticValues = FloatArray(3)
    private val rotationMatrix = FloatArray(9)
    private val displayRotationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)
    private var hasGravity = false
    private var hasMagneticField = false
    private var displayRotation = Surface.ROTATION_0

    private var lastAccel: VectorReading? = null
    private var lastGyro: VectorReading? = null
    private var currentHeading: Float? = null

    fun start(displayRotation: Int) {
        this.displayRotation = displayRotation
        val availability = mutableListOf<String>()
        register(accelerometer, "accelerometer", availability)
        register(gyroscope, "gyroscope", availability)
        register(magnetometer, "magnetometer", availability)

        onReadings {
            copy(
                sensorStatus = if (availability.isEmpty()) {
                    "Accelerometer, gyroscope, and magnetometer active"
                } else {
                    "Unavailable or inaccessible: ${availability.joinToString() }"
                },
            )
        }
        updateHeading(displayRotation)
    }

    fun stop() {
        try {
            sensorManager.unregisterListener(this)
        } catch (_: Throwable) {}
        hasGravity = false
        hasMagneticField = false
    }

    override fun onSensorChanged(event: SensorEvent) {
        val reading = VectorReading(event.values[0], event.values[1], event.values[2])
        val nowNanos = event.timestamp

        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                event.values.copyInto(gravityValues)
                hasGravity = true
                lastAccel = reading
                onReadings { copy(accelerometer = reading) }
                updateHeading(displayRotation)
                movementDetector.processSensors(reading, lastGyro, currentHeading, nowNanos)
            }

            Sensor.TYPE_GYROSCOPE -> {
                lastGyro = reading
                onReadings { copy(gyroscope = reading) }
                movementDetector.processSensors(lastAccel, reading, currentHeading, nowNanos)
            }

            Sensor.TYPE_MAGNETIC_FIELD -> {
                event.values.copyInto(magneticValues)
                hasMagneticField = true
                onReadings { copy(magnetometer = reading) }
                updateHeading(displayRotation)
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        if (sensor?.type == Sensor.TYPE_MAGNETIC_FIELD && accuracy == SensorManager.SENSOR_STATUS_UNRELIABLE) {
            onReadings { copy(sensorStatus = "Compass readings are unreliable; move away from magnetic interference") }
        }
    }

    private fun register(sensor: Sensor?, name: String, unavailable: MutableList<String>) {
        if (sensor == null) {
            unavailable += "$name sensor missing"
            return
        }

        val registered = try {
            sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_GAME)
        } catch (_: SecurityException) {
            false
        }
        if (!registered) unavailable += "$name access failed"
    }

    private fun updateHeading(displayRotation: Int) {
        if (!hasGravity || !hasMagneticField) return

        // Compute rotation matrix using accelerometer and magnetometer sensor fusion
        if (!SensorManager.getRotationMatrix(rotationMatrix, null, gravityValues, magneticValues)) {
            return
        }

        // Remap coordinate system for upright / vertical device usage (phone held in portrait view facing forward)
        // AXIS_X to AXIS_X, AXIS_Y to AXIS_Z correctly projects device azimuth when held vertically facing forward.
        val (axisX, axisY) = when (displayRotation) {
            Surface.ROTATION_90 -> SensorManager.AXIS_Y to SensorManager.AXIS_MINUS_X
            Surface.ROTATION_180 -> SensorManager.AXIS_MINUS_X to SensorManager.AXIS_MINUS_Y
            Surface.ROTATION_270 -> SensorManager.AXIS_MINUS_Y to SensorManager.AXIS_X
            else -> SensorManager.AXIS_X to SensorManager.AXIS_Z
        }

        SensorManager.remapCoordinateSystem(rotationMatrix, axisX, axisY, displayRotationMatrix)
        SensorManager.getOrientation(displayRotationMatrix, orientation)

        // Normalize heading between 0° and 359° clockwise from North
        var heading = Math.toDegrees(orientation[0].toDouble()).toFloat()
        heading = (heading % 360f + 360f) % 360f
        
        currentHeading = heading
        Log.d(TAG, "[COMPASS-DEBUG] Raw Accel: ${lastAccel?.x},${lastAccel?.y},${lastAccel?.z} | Mag: ${magneticValues[0]},${magneticValues[1]},${magneticValues[2]} | Heading: ${"%.1f".format(heading)}°")
        onReadings { copy(headingDegrees = heading) }
    }

    companion object {
        private const val TAG = "PhoneSensorTracker"
    }
}