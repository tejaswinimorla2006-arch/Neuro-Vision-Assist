package com.neurovisionassist.phone

import android.util.Log

class AutomaticWaypointTracker(
    private val onStateUpdate: (TrackingUiState.() -> TrackingUiState) -> Unit,
    private val onSpeakInstruction: (String) -> Unit,
    private val onSendPiEvent: ((NavigationPayload) -> Unit)? = null,
) {
    private fun safeLogD(tag: String, msg: String) {
        try {
            Log.d(tag, msg)
        } catch (_: Throwable) {
            println("[$tag] $msg")
        }
    }

    fun checkHeadingAndRoute(calibratedHeading: Float?, uiState: TrackingUiState) {
        // Compass heading is tracked internally for orientation/debugging but does not generate spoken off-route alerts.
        val routePlanner = uiState.routePlanner
        if (!routePlanner.isNavigating || routePlanner.isPaused || calibratedHeading == null) return
        val currentStep = routePlanner.calculatedRoute?.steps?.getOrNull(routePlanner.currentStepIndex) ?: return
        
        onStateUpdate {
            copy(
                routePlanner = routePlanner.copy(
                    expectedHeadingDegrees = currentStep.headingDegrees,
                    offRouteWarning = null,
                ),
            )
        }
    }

    fun processStep(stepLength: Float, uiState: TrackingUiState) {
        val routePlanner = uiState.routePlanner
        if (!routePlanner.isNavigating || routePlanner.isPaused) return
        val route = routePlanner.calculatedRoute ?: return
        val steps = route.steps
        val currentIndex = routePlanner.currentStepIndex

        if (currentIndex >= steps.size) return // Destination fully reached

        val currentStep = steps[currentIndex]
        val newWalkedOnStep = routePlanner.distanceWalkedOnCurrentStep + stepLength
        val targetDistance = currentStep.distanceMeters

        val reachedWaypoint = targetDistance <= 0.05f || (newWalkedOnStep >= targetDistance || (targetDistance - newWalkedOnStep) <= 0.35f)

        val rawHeading = uiState.headingDegrees
        val currentHeading = if (rawHeading != null) ((rawHeading + routePlanner.mapHeadingOffsetDegrees) % 360f + 360f) % 360f else null

        if (reachedWaypoint) {
            val nextIndex = currentIndex + 1
            val nextStep = steps.getOrNull(nextIndex)
            val isFinalDestination = nextIndex >= steps.size

            val remainingDist = calculateRemainingDistance(steps, nextIndex, 0f)

            safeLogD(
                TAG,
                "Waypoint Reached! Advanced from step $currentIndex (${currentStep.targetNodeName}) to step $nextIndex (${nextStep?.targetNodeName}). Walked: ${"%.2f".format(newWalkedOnStep)}m / ${"%.2f".format(targetDistance)}m",
            )

            val updatedInstruction = nextStep?.instruction ?: "Destination reached: ${route.destinationNode.name}."
            val speechText = updatedInstruction.replace("\n", " ")

            safeLogD(TAG, "[PI-STREAM] Instruction generated: $speechText (Step ${nextIndex + 1}/${steps.size})")

            onStateUpdate {
                copy(
                    routePlanner = routePlanner.copy(
                        currentStepIndex = nextIndex,
                        distanceWalkedOnCurrentStep = 0f,
                        remainingRouteDistanceMeters = remainingDist,
                        isNavigating = !isFinalDestination,
                        expectedHeadingDegrees = nextStep?.headingDegrees,
                        offRouteWarning = null,
                    ),
                )
            }

            onSpeakInstruction(speechText)

            val payload = NavigationPayload(
                type = if (isFinalDestination) "NAVIGATION_COMPLETED" else "WAYPOINT_REACHED",
                instruction = speechText,
                distanceMeters = nextStep?.distanceMeters ?: 0f,
                remainingDistanceMeters = remainingDist,
                distanceWalkedStep = 0f,
                stepDistance = nextStep?.distanceMeters ?: currentStep.distanceMeters,
                currentStep = nextIndex + 1,
                totalSteps = steps.size,
                currentNode = nextStep?.targetNodeName ?: route.destinationNode.name,
                nextNode = steps.getOrNull(nextIndex + 1)?.targetNodeName ?: route.destinationNode.name,
                heading = currentHeading,
                expectedHeading = nextStep?.headingDegrees,
            )
            onSendPiEvent?.invoke(payload)
        } else {
            val remainingDist = calculateRemainingDistance(steps, currentIndex, newWalkedOnStep)

            onStateUpdate {
                copy(
                    routePlanner = routePlanner.copy(
                        distanceWalkedOnCurrentStep = newWalkedOnStep,
                        remainingRouteDistanceMeters = remainingDist,
                    ),
                )
            }

            val payload = NavigationPayload(
                type = "DISTANCE_UPDATE",
                instruction = null, // DISTANCE_UPDATE updates remaining distance without repeating instruction text
                distanceMeters = (currentStep.distanceMeters - newWalkedOnStep).coerceAtLeast(0f),
                remainingDistanceMeters = remainingDist,
                distanceWalkedStep = newWalkedOnStep,
                stepDistance = currentStep.distanceMeters,
                currentStep = currentIndex + 1,
                totalSteps = steps.size,
                currentNode = currentStep.targetNodeName,
                nextNode = steps.getOrNull(currentIndex + 1)?.targetNodeName ?: route.destinationNode.name,
                heading = currentHeading,
                expectedHeading = currentStep.headingDegrees,
            )
            onSendPiEvent?.invoke(payload)
        }
    }

    fun calculateRemainingDistance(
        steps: List<RouteStep>,
        currentIndex: Int,
        walkedOnCurrentStep: Float,
    ): Float {
        if (steps.isEmpty() || currentIndex >= steps.size) return 0f
        var total = (steps[currentIndex].distanceMeters - walkedOnCurrentStep).coerceAtLeast(0f)
        for (i in (currentIndex + 1) until steps.size) {
            total += steps[i].distanceMeters
        }
        return total
    }

    companion object {
        private const val TAG = "WaypointTracker"
    }
}