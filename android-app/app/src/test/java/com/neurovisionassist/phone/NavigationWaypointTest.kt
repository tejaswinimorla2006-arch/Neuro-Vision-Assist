package com.neurovisionassist.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NavigationWaypointTest {

    @Test
    fun testAutomaticWaypointTrackerTransitionsAndPayloads() {
        val startNode = MapNode("door_l209", "L-209", -1.5f, 10.84f, NodeType.DOORWAY)
        val destNode = MapNode("door_l208", "L-208", -1.5f, 2.0f, NodeType.DOORWAY)
        val steps = listOf(
            RouteStep("Exit L-209 and walk straight for 1.5 metres.", 1.5f, 345f, "jn_l209"),
            RouteStep("Turn left towards Junction at L-208/L-213, then walk 8.8 metres.", 8.84f, 253f, "jn_l208"),
            RouteStep("Turn left through the L-208 entrance, then walk 1.5 metres.", 1.5f, 270f, "door_l208"),
            RouteStep("Enter L-208. You have reached your destination.", 0f, 270f, "L-208")
        )
        val route = RouteResult(startNode, destNode, 11.84f, listOf(startNode, destNode), steps)

        var uiState = TrackingUiState(
            routePlanner = RoutePlannerState(
                isNavigating = true,
                calculatedRoute = route,
                currentStepIndex = 0,
                distanceWalkedOnCurrentStep = 0f,
                remainingRouteDistanceMeters = route.totalDistanceMeters
            )
        )

        val capturedEvents = mutableListOf<NavigationPayload>()
        val tracker = AutomaticWaypointTracker(
            onStateUpdate = { transform ->
                uiState = uiState.transform()
                uiState
            },
            onSpeakInstruction = {},
            onSendPiEvent = { payload ->
                capturedEvents.add(payload)
            }
        )

        repeat(2) {
            tracker.processStep(1.0f, uiState)
        }
        assertEquals("Current step index should be 1", 1, uiState.routePlanner.currentStepIndex)
        assertTrue("Navigation should remain active", uiState.routePlanner.isNavigating)

        repeat(9) {
            tracker.processStep(1.0f, uiState)
        }
        assertEquals("Current step index should be 2", 2, uiState.routePlanner.currentStepIndex)
        assertTrue("Navigation should remain active", uiState.routePlanner.isNavigating)

        repeat(2) {
            tracker.processStep(1.0f, uiState)
        }
        assertEquals("Current step index should be 3 (final arrival step)", 3, uiState.routePlanner.currentStepIndex)
        assertTrue("Navigation should remain active until arrival step completes", uiState.routePlanner.isNavigating)

        tracker.processStep(0.1f, uiState)
        assertFalse("Navigation should be completed only after final arrival step", uiState.routePlanner.isNavigating)
        assertEquals("Distance remaining should be 0", 0f, uiState.routePlanner.remainingRouteDistanceMeters, 0.1f)
    }

    @Test
    fun testL209ToLH201RouteGeneration() {
        val route = IndoorMapRepository.calculateShortestPath("L-209", "LH-201")
        assertNotNull("Route from L-209 to LH-201 should not be null (HTTP 200 equivalent)", route)
        
        println("=== L-209 -> LH-201 ROUTE AUDIT ===")
        println("Total Distance: ${"%.2f".format(route!!.totalDistanceMeters)} metres")
        for ((idx, step) in route.steps.withIndex()) {
            println("  Step ${idx + 1}: ${step.instruction} | Dist: ${"%.2f".format(step.distanceMeters)}m | Heading: ${"%.1f".format(step.headingDegrees)}°")
        }
        println("======================================")

        assertTrue("Route must start at L-209", route.startNode.id.contains("l209", ignoreCase = true))
        assertTrue("Route must end at LH-201", route.destinationNode.id.contains("lh201", ignoreCase = true))
        assertTrue("Route must contain valid non-empty steps", route.steps.isNotEmpty())
    }

    @Test
    fun testAllReferenceAndMappedLocations() {
        val locations = IndoorMapRepository.userLocations.map { it.id }
        assertTrue("User locations should be present", locations.isNotEmpty())

        val samplePairs = listOf(
            "L-209" to "LH-201",
            "LH-207" to "LH-204",
            "LH-205" to "LH-204",
            "L-208" to "LH-201"
        )

        for ((start, dest) in samplePairs) {
            val route = IndoorMapRepository.calculateShortestPath(start, dest)
            assertNotNull("Route from $start to $dest must exist", route)
            assertTrue("Route must have steps", route!!.steps.isNotEmpty())
        }
    }
}