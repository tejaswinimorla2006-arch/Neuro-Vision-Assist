package com.neurovisionassist.phone

import android.util.Log
import kotlin.math.abs

class AutomaticWaypointTracker(
    private val onStateUpdate: (TrackingUiState.() -> TrackingUiState) -> Unit,
    private val onSpeakInstruction: (String) -> Unit,
    private val onSendPiEvent: ((NavigationPayload) -> Unit)? = null,
) {
    private var offRouteCount = 0

    fun checkHeadingAndRoute(calibratedHeading: Float?, uiState: TrackingUiState) {
        val routePlanner = uiState.routePlanner
        if (!routePlanner.isNavigating || routePlanner.isPaused || calibratedHeading == null) return
        val route = routePlanner.calculatedRoute ?: return
        val steps = route.steps
        val currentIndex = routePlanner.currentStepIndex
        val currentStep = steps.getOrNull(currentIndex) ?: return

        val expectedHeading = currentStep.headingDegrees
        val headingDiff = abs(normalizeAngle(calibratedHeading - expectedHeading))

        // Check for heading deviation when walking
        if (uiState.movementTest.motionState == "Walking" && headingDiff > 60f) {
            offRouteCount++
            if (offRouteCount >= 10 && routePlanner.offRouteWarning == null) {
                val correctionMsg = "Wrong heading. Face heading %.0f degrees.".format(expectedHeading)
                Log.w(TAG, "Off-route warning: $correctionMsg (Current: %.1f, Expected: %.1f)".format(calibratedHeading, expectedHeading))

                onStateUpdate {
                    copy(
                        routePlanner = routePlanner.copy(
                            offRouteWarning = correctionMsg,
                            expectedHeadingDegrees = expectedHeading,
                        ),
                    )
                }

                // Send correction event to Pi
                onSendPiEvent?.invoke(
                    NavigationPayload(
                        type = "NAVIGATION_INSTRUCTION",
                        instruction = correctionMsg,
                        distanceRemainingMeters = routePlanner.remainingRouteDistanceMeters,
                        currentLocation = currentStep.targetNodeName,
                        nextLocation = steps.getOrNull(currentIndex + 1)?.targetNodeName ?: route.destinationNode.name,
                        heading = calibratedHeading,
                        expectedHeading = expectedHeading,
                    ),
                )
            }
        } else {
            if (offRouteCount > 0) {
                offRouteCount = 0
                if (routePlanner.offRouteWarning != null) {
                    onStateUpdate {
                        copy(
                            routePlanner = routePlanner.copy(
                                offRouteWarning = null,
                                expectedHeadingDegrees = expectedHeading,
                            ),
                        )
                    }
                }
            } else {
                onStateUpdate {
                    copy(
                        routePlanner = routePlanner.copy(
                            expectedHeadingDegrees = expectedHeading,
                        ),
                    )
                }
            }
        }
    }

    fun processStep(stepLength: Float, uiState: TrackingUiState) {
        val routePlanner = uiState.routePlanner
        if (!routePlanner.isNavigating || routePlanner.isPaused) return
        val route = routePlanner.calculatedRoute ?: return
        val steps = route.steps
        val currentIndex = routePlanner.currentStepIndex

        if (currentIndex >= steps.size - 1) return // Destination reached

        val currentStep = steps[currentIndex]
        val newWalkedOnStep = routePlanner.distanceWalkedOnCurrentStep + stepLength
        val targetDistance = currentStep.distanceMeters

        val reachedWaypoint = targetDistance > 0f && (newWalkedOnStep >= targetDistance || (targetDistance - newWalkedOnStep) <= 0.35f)

        val rawHeading = uiState.headingDegrees
        val currentHeading = if (rawHeading != null) ((rawHeading + routePlanner.mapHeadingOffsetDegrees) % 360f + 360f) % 360f else null

        if (reachedWaypoint) {
            val nextIndex = currentIndex + 1
            val nextStep = steps.getOrNull(nextIndex)
            val isFinalDestination = nextIndex >= steps.size - 1

            val remainingDist = calculateRemainingDistance(steps, nextIndex, 0f)

            Log.d(
                TAG,
                "Waypoint Reached! Advanced from step $currentIndex (${currentStep.targetNodeName}) to step $nextIndex (${nextStep?.targetNodeName}). Walked: ${"%.2f".format(newWalkedOnStep)}m / ${"%.2f".format(targetDistance)}m",
            )

            val updatedInstruction = nextStep?.instruction ?: "Destination reached: ${route.destinationNode.name}."

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

            val speechText = updatedInstruction.replace("\n", " ")
            onSpeakInstruction(speechText)

            // Send WAYPOINT_REACHED / NAVIGATION_COMPLETED event to Pi
            onSendPiEvent?.invoke(
                NavigationPayload(
                    type = if (isFinalDestination) "NAVIGATION_COMPLETED" else "WAYPOINT_REACHED",
                    instruction = speechText,
                    distanceRemainingMeters = remainingDist,
                    currentLocation = nextStep?.targetNodeName ?: route.destinationNode.name,
                    nextLocation = steps.getOrNull(nextIndex + 1)?.targetNodeName ?: route.destinationNode.name,
                    heading = currentHeading,
                    expectedHeading = nextStep?.headingDegrees,
                ),
            )
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

            // Send DISTANCE_UPDATE event
            onSendPiEvent?.invoke(
                NavigationPayload(
                    type = "DISTANCE_UPDATE",
                    instruction = null,
                    distanceRemainingMeters = remainingDist,
                    currentLocation = currentStep.targetNodeName,
                    nextLocation = steps.getOrNull(currentIndex + 1)?.targetNodeName ?: route.destinationNode.name,
                    heading = currentHeading,
                    expectedHeading = currentStep.headingDegrees,
                ),
            )
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

    private fun normalizeAngle(angle: Float): Float {
        var a = (angle % 360f + 360f) % 360f
        if (a > 180f) a -= 360f
        return a
    }

    companion object {
        private const val TAG = "WaypointTracker"
    }
}