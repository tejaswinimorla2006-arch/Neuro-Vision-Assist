package com.neurovisionassist.phone

import java.util.PriorityQueue

data class MapNode(
    val id: String,
    val name: String,
    val isRoom: Boolean = true,
)

data class MapEdge(
    val fromId: String,
    val toId: String,
    val distanceMeters: Float,
    val headingDegrees: Float,
    val description: String = "",
)

data class RouteStep(
    val instruction: String,
    val distanceMeters: Float,
    val headingDegrees: Float,
    val targetNodeName: String,
)

data class RouteResult(
    val startNode: MapNode,
    val destinationNode: MapNode,
    val totalDistanceMeters: Float,
    val pathNodes: List<MapNode>,
    val steps: List<RouteStep>,
)

object IndoorMapRepository {
    val nodes: List<MapNode> = listOf(
        // 21 User Locations from ISE_FloorMap.jpeg
        MapNode("LH-201", "LH-201"),
        MapNode("LH-202", "LH-202"),
        MapNode("LH-203", "LH-203"),
        MapNode("LH-204", "LH-204"),
        MapNode("LH-205", "LH-205"),
        MapNode("LH-206", "LH-206"),
        MapNode("LH-207", "LH-207"),
        MapNode("L-208", "L-208"),
        MapNode("L-209", "L-209"),
        MapNode("L-210", "L-210"),
        MapNode("L-211", "L-211"),
        MapNode("L-212", "L-212"),
        MapNode("L-213", "L-213"),
        MapNode("Student Lounge", "Student Lounge"),
        MapNode("Library", "Library"),
        MapNode("Staff Room", "Staff Room"),
        MapNode("Staff WC", "Staff WC"),
        MapNode("Washroom", "Washroom"),
        MapNode("Stairs", "Stairs"),
        MapNode("Lift", "Lift"),
        MapNode("Balcony", "Balcony"),

        // Internal Corridor Junction Nodes
        MapNode("J_Lounge", "Lounge Junction", isRoom = false),
        MapNode("J_1", "Corridor Junction 1", isRoom = false),
        MapNode("J_2", "Corridor Junction 2", isRoom = false),
        MapNode("J_3", "Corridor Junction 3", isRoom = false),
        MapNode("J_4", "Corridor Junction 4", isRoom = false),
        MapNode("J_5", "Corridor Junction 5", isRoom = false),
        MapNode("J_6", "Corridor Junction 6", isRoom = false),
        MapNode("J_7", "Corridor Junction 7", isRoom = false),
    )

    private val nodesById = nodes.associateBy { it.id }

    val userLocations: List<MapNode> = nodes.filter { it.isRoom }.sortedBy { it.name }

    val edges: List<MapEdge> = buildList {
        fun addBi(from: String, to: String, distance: Float, heading: Float, desc: String = "") {
            add(MapEdge(from, to, distance, heading, desc))
            val reverseHeading = (heading + 180f) % 360f
            add(MapEdge(to, from, distance, reverseHeading, desc))
        }

        // Student Lounge area connections (from ISE_FloorMap.jpeg)
        addBi("Student Lounge", "J_Lounge", 8.26f, 0f, "Main hallway towards corridor")
        addBi("Stairs", "J_Lounge", 3.50f, 90f, "Stairs access")
        addBi("Lift", "J_Lounge", 3.00f, 270f, "Elevator lobby")

        // Main Corridor spine (ISE 2nd Floor layout)
        addBi("J_Lounge", "J_1", 2.13f, 270f, "Main corridor segment 1")
        addBi("J_1", "J_2", 5.60f, 270f, "Main corridor segment 2")
        addBi("J_2", "J_3", 5.60f, 270f, "Main corridor segment 3")
        addBi("J_3", "J_4", 4.00f, 270f, "Main corridor segment 4")
        addBi("J_4", "J_5", 5.60f, 270f, "Main corridor segment 5")
        addBi("J_5", "J_6", 5.60f, 270f, "Main corridor segment 6")
        addBi("J_6", "J_7", 4.50f, 270f, "Corridor end segment")

        // Room connections off Corridor Junctions
        addBi("J_1", "LH-201", 2.50f, 0f, "LH-201 entrance")
        addBi("J_1", "L-208", 2.50f, 180f, "L-208 entrance")
        addBi("J_1", "Library", 6.00f, 0f, "Library entrance")

        addBi("J_2", "LH-202", 2.50f, 0f, "LH-202 entrance")
        addBi("J_2", "L-209", 2.50f, 180f, "L-209 entrance")
        addBi("J_2", "Staff Room", 4.20f, 180f, "Staff Room entrance")

        addBi("J_3", "LH-203", 2.50f, 0f, "LH-203 entrance")
        addBi("J_3", "L-210", 2.50f, 180f, "L-210 entrance")
        addBi("J_3", "Staff WC", 3.10f, 180f, "Staff WC entrance")

        addBi("J_4", "LH-204", 2.50f, 0f, "LH-204 entrance")
        addBi("J_4", "L-211", 2.50f, 180f, "L-211 entrance")
        addBi("J_4", "Washroom", 3.50f, 180f, "Public Washroom entrance")

        addBi("J_5", "LH-205", 2.50f, 0f, "LH-205 entrance")
        addBi("J_5", "L-212", 2.50f, 180f, "L-212 entrance")

        addBi("J_6", "LH-206", 2.67f, 0f, "LH-206 entrance")
        addBi("J_6", "L-213", 2.50f, 180f, "L-213 entrance")

        addBi("J_7", "LH-207", 3.00f, 0f, "LH-207 entrance")
        addBi("J_7", "Balcony", 5.00f, 270f, "Balcony exit")
    }

    private val adjacencyList: Map<String, List<MapEdge>> = edges.groupBy { it.fromId }

    fun calculateShortestPath(startId: String, destId: String): RouteResult? {
        val startNode = nodesById[startId] ?: return null
        val destNode = nodesById[destId] ?: return null

        if (startId == destId) {
            return RouteResult(
                startNode = startNode,
                destinationNode = destNode,
                totalDistanceMeters = 0f,
                pathNodes = listOf(startNode),
                steps = listOf(RouteStep("Destination: ${destNode.name}.", 0f, 0f, destNode.name)),
            )
        }

        // Dijkstra's Shortest Path Algorithm
        val distances = mutableMapOf<String, Float>().withDefault { Float.POSITIVE_INFINITY }
        val previousEdge = mutableMapOf<String, MapEdge>()
        val pq = PriorityQueue<Pair<String, Float>>(compareBy { it.second })

        distances[startId] = 0f
        pq.add(startId to 0f)

        while (pq.isNotEmpty()) {
            val top = pq.poll() ?: break
            val currentId = top.first
            val currentDist = top.second

            if (currentDist > distances.getValue(currentId)) continue
            if (currentId == destId) break

            val neighbors = adjacencyList[currentId] ?: emptyList()
            for (edge in neighbors) {
                val newDist = currentDist + edge.distanceMeters
                if (newDist < distances.getValue(edge.toId)) {
                    distances[edge.toId] = newDist
                    previousEdge[edge.toId] = edge
                    pq.add(edge.toId to newDist)
                }
            }
        }

        if (!previousEdge.containsKey(destId)) {
            return null
        }

        val edgePath = mutableListOf<MapEdge>()
        var curr = destId
        while (curr != startId) {
            val edge = previousEdge[curr] ?: break
            edgePath.add(0, edge)
            curr = edge.fromId
        }

        val pathNodes = mutableListOf(startNode)
        for (edge in edgePath) {
            nodesById[edge.toId]?.let { pathNodes.add(it) }
        }

        val totalDistance = distances.getValue(destId)
        val steps = generateTurnByTurnInstructions(edgePath, destNode.name)

        return RouteResult(
            startNode = startNode,
            destinationNode = destNode,
            totalDistanceMeters = totalDistance,
            pathNodes = pathNodes,
            steps = steps,
        )
    }

    private fun generateTurnByTurnInstructions(
        edges: List<MapEdge>,
        destinationName: String,
    ): List<RouteStep> {
        if (edges.isEmpty()) return emptyList()

        val steps = mutableListOf<RouteStep>()

        for (i in edges.indices) {
            val edge = edges[i]
            val targetName = nodesById[edge.toId]?.name ?: edge.toId

            val instructionText = if (i == 0) {
                "Walk straight for %.2f m.".format(edge.distanceMeters)
            } else {
                val prevEdge = edges[i - 1]
                val turnAngle = normalizeAngle(edge.headingDegrees - prevEdge.headingDegrees)

                when {
                    turnAngle in -30f..30f -> "Continue straight for %.2f m.".format(edge.distanceMeters)
                    turnAngle in 30f..150f -> "Turn right.\nWalk %.2f m.".format(edge.distanceMeters)
                    turnAngle in -150f..-30f -> "Turn left.\nWalk %.2f m.".format(edge.distanceMeters)
                    else -> "Turn around.\nWalk %.2f m.".format(edge.distanceMeters)
                }
            }

            steps.add(
                RouteStep(
                    instruction = instructionText,
                    distanceMeters = edge.distanceMeters,
                    headingDegrees = edge.headingDegrees,
                    targetNodeName = targetName,
                ),
            )
        }

        steps.add(
            RouteStep(
                instruction = "Destination: $destinationName.",
                distanceMeters = 0f,
                headingDegrees = edges.last().headingDegrees,
                targetNodeName = destinationName,
            ),
        )

        return steps
    }

    private fun normalizeAngle(angle: Float): Float {
        var a = (angle % 360f + 360f) % 360f
        if (a > 180f) a -= 360f
        return a
    }
}