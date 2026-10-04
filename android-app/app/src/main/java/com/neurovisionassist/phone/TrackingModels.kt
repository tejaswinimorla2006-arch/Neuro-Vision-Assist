package com.neurovisionassist.phone

data class VectorReading(
    val x: Float,
    val y: Float,
    val z: Float,
)

data class MovementTestState(
    val isTesting: Boolean = false,
    val stepCount: Int = 0,
    val estimatedDistanceMeters: Float = 0f,
    val lastStepLengthMeters: Float = 0f,
    val motionState: String = "Stopped",
    val stepIntervalMs: Long = 0L,
)

data class RoutePlannerState(
    val selectedStartNodeId: String = "Student Lounge",
    val selectedDestNodeId: String = "LH-206",
    val calculatedRoute: RouteResult? = null,
    val isNavigating: Boolean = false,
    val isPaused: Boolean = false,
    val currentStepIndex: Int = 0,
    val distanceWalkedOnCurrentStep: Float = 0f,
    val remainingRouteDistanceMeters: Float = 0f,
    val expectedHeadingDegrees: Float? = null,
    val mapHeadingOffsetDegrees: Float = 0f,
    val offRouteWarning: String? = null,
    val piHost: String = "192.168.118.202",
    val piPort: Int = 8765,
    val piConnectionStatus: String = "Disconnected",
    val lastSentMessage: String = "None",
    val lastPiResponse: String = "None",
)

data class TrackingUiState(
    val selectedTab: Int = 0, // 0 = Overview, 1 = Movement Test, 2 = Route Planner, 3 = Debug / Pi
    val status: String = "Stopped",
    val arTrackingState: String = "Not started",
    val sensorStatus: String = "Sensors not active",
    val headingDegrees: Float? = null,
    val accelerometer: VectorReading? = null,
    val gyroscope: VectorReading? = null,
    val magnetometer: VectorReading? = null,
    val poseX: Float? = null,
    val poseY: Float? = null,
    val poseZ: Float? = null,
    val isTracking: Boolean = false,
    val message: String? = null,
    val movementTest: MovementTestState = MovementTestState(),
    val routePlanner: RoutePlannerState = RoutePlannerState(),
)