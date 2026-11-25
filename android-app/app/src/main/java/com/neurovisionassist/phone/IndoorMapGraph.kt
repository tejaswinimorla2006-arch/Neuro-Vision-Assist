package com.neurovisionassist.phone

import java.util.PriorityQueue
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot

enum class NodeType { ROOM, DOORWAY, JUNCTION, STAIRS, LIFT, BALCONY }

data class MapNode(
    val id: String,
    val name: String,
    val x: Float, // metres (X increases East)
    val y: Float, // metres (Y increases South)
    val nodeType: NodeType,
    val isRoom: Boolean = (nodeType == NodeType.DOORWAY),
    val isVerified: Boolean = true
)

data class MapEdge(
    val fromId: String,
    val toId: String,
    val distanceMeters: Float,
    val headingDegrees: Float,
    val description: String = ""
)

data class RouteStep(
    val instruction: String,
    val distanceMeters: Float,
    val headingDegrees: Float,
    val targetNodeName: String
)

data class RouteResult(
    val startNode: MapNode,
    val destinationNode: MapNode,
    val totalDistanceMeters: Float,
    val pathNodes: List<MapNode>,
    val steps: List<RouteStep>
)

object IndoorMapRepository {

    val nodes: List<MapNode> = listOf(
        // ── ENTRANCE-TO-ENTRANCE DOORWAY NODES (With distinct offset from junctions) ──
        MapNode("door_lh201", "LH-201", 35.88f, 11.56f, NodeType.DOORWAY),
        MapNode("door_lh202", "LH-202", 25.82f, 11.56f, NodeType.DOORWAY),
        MapNode("door_lh203", "LH-203", 17.90f, 11.56f, NodeType.DOORWAY),
        MapNode("door_lh204", "LH-204", 9.92f, 9.06f, NodeType.DOORWAY),
        MapNode("door_lh205", "LH-205", 20.0f, -2.5f, NodeType.DOORWAY),
        MapNode("door_lh206", "LH-206", 9.92f, -2.5f, NodeType.DOORWAY),
        MapNode("door_lh207", "LH-207", -1.0f, -1.5f, NodeType.DOORWAY),
        MapNode("door_l208", "L-208", -1.5f, 2.0f, NodeType.DOORWAY),
        MapNode("door_l209", "L-209", -1.5f, 10.84f, NodeType.DOORWAY),
        MapNode("door_l210", "L-210", -1.5f, 19.68f, NodeType.DOORWAY),
        MapNode("door_l211", "L-211", 0.0f, 19.68f, NodeType.DOORWAY),
        MapNode("door_l212", "L-212", 0.0f, 10.84f, NodeType.DOORWAY),
        MapNode("door_l213", "L-213", 0.0f, 2.0f, NodeType.DOORWAY),
        MapNode("door_staff", "Staff Room", 27.0f, -2.5f, NodeType.DOORWAY),
        MapNode("door_staff_wc", "Staff WC", 31.0f, -2.5f, NodeType.DOORWAY),
        MapNode("door_washroom", "Washroom", 14.0f, -2.5f, NodeType.DOORWAY),
        MapNode("door_library", "Library", 35.88f, 11.56f, NodeType.DOORWAY),
        MapNode("door_lounge", "Student Lounge", 35.88f, 11.56f, NodeType.DOORWAY),

        // ── NORTH CORRIDOR JUNCTIONS ──
        MapNode("jn_top_w",    "North-West Junction (0m)",        0.0f, -1.5f, NodeType.JUNCTION),
        MapNode("jn_top_9",    "North Corridor Junction (9.92m)", 9.92f, -1.5f, NodeType.JUNCTION),
        MapNode("jn_top_15",   "North Corridor Junction (20m)",   20.0f, -1.5f, NodeType.JUNCTION),
        MapNode("jn_top_245",  "North Corridor Junction (27.5m)", 27.5f, -1.5f, NodeType.JUNCTION),
        MapNode("jn_top_stair","North-East Junction (35.88m)",    35.88f, -1.5f, NodeType.JUNCTION),

        // ── SOUTH CORRIDOR JUNCTIONS ──
        MapNode("jn_lh204",    "Junction at LH-204",          9.92f, 10.06f, NodeType.JUNCTION),
        MapNode("jn_lh203",    "Junction at LH-203",          17.90f, 10.06f, NodeType.JUNCTION),
        MapNode("jn_lh202",    "Junction at LH-202",          25.82f, 10.06f, NodeType.JUNCTION),
        MapNode("jn_lh201",    "Junction at LH-201",          35.88f, 10.06f, NodeType.JUNCTION),

        // ── OTHER JUNCTIONS & FACILITIES ──
        MapNode("jn_l208",     "Junction at L-208/L-213",     0.0f, 2.0f, NodeType.JUNCTION),
        MapNode("jn_l209",     "Junction at L-209/L-212",     0.0f, 10.84f, NodeType.JUNCTION),
        MapNode("jn_l210",     "Junction at L-210/L-211",     0.0f, 19.68f, NodeType.JUNCTION),
        MapNode("jn_lift_w",   "West Stair/Lift Junction",    0.0f, 24.08f, NodeType.JUNCTION),
        MapNode("Lift",        "Lift",                        31.0f, -1.5f, NodeType.LIFT),
        MapNode("Stairs (West)","Stairs (West)",              4.5f, 24.08f, NodeType.STAIRS),
        MapNode("Stairs (East)","Stairs (East)",              34.0f, -1.5f, NodeType.STAIRS),
        MapNode("Balcony",     "Balcony",                     -5.0f, 19.68f, NodeType.BALCONY),
    )

    private val nodesById = nodes.associateBy { it.id }
    val userLocations: List<MapNode> = nodes.filter { it.nodeType == NodeType.DOORWAY }.sortedBy { it.name }

    val edges: List<MapEdge> = buildList {
        fun connect(fromId: String, toId: String, customHeading: Float? = null, desc: String = "") {
            val n1 = nodesById[fromId] ?: throw IllegalArgumentException("Missing node $fromId")
            val n2 = nodesById[toId] ?: throw IllegalArgumentException("Missing node $toId")
            val dx = n2.x - n1.x
            val dy = n2.y - n1.y
            val dist = hypot(dx, dy)
            if (dist < 0.05f) return

            val rad = atan2(dx, -dy)
            var deg = Math.toDegrees(rad.toDouble()).toFloat()
            if (deg < 0f) deg += 360f

            val forwardHeading = customHeading ?: deg
            add(MapEdge(fromId, toId, dist, forwardHeading, desc))

            var revHeading = forwardHeading + 180f
            if (revHeading >= 360f) revHeading -= 360f
            add(MapEdge(toId, fromId, dist, revHeading, desc))
        }

        // NORTH CORRIDOR ENTRANCES TO JUNCTIONS
        connect("door_lh207", "jn_top_w")
        connect("door_lh206", "jn_top_9")
        connect("door_washroom", "jn_top_w")
        connect("door_lh205", "jn_top_15")
        connect("door_staff", "jn_top_15")
        connect("door_staff_wc", "jn_top_245")

        // NORTH CORRIDOR SEGMENTS
        connect("jn_top_w", "jn_top_9")
        connect("jn_top_9", "jn_top_15")
        connect("jn_top_15", "jn_top_245")
        connect("jn_top_245", "jn_top_stair", desc = "Lift on your right")
        connect("jn_top_stair", "Stairs (East)")
        connect("jn_top_stair", "Lift")

        // WEST VERTICAL CORRIDOR & ENTRANCES
        connect("door_l208", "jn_l208", customHeading = 253f)
        connect("door_l213", "jn_l208")
        connect("door_l209", "jn_l209", customHeading = 345f)
        connect("door_l212", "jn_l209", customHeading = 160f)
        connect("door_l210", "jn_l210")
        connect("door_l211", "jn_l210")

        connect("jn_top_w", "jn_l208")
        connect("jn_l208", "jn_l209")
        connect("jn_l209", "jn_l210", customHeading = 75f)
        connect("jn_l210", "jn_lift_w")
        connect("jn_lift_w", "Stairs (West)")
        connect("jn_l210", "Balcony")

        // SOUTH CORRIDOR ENTRANCES TO JUNCTIONS (Bidirectional connections)
        connect("door_lh204", "jn_lh204")
        connect("door_lh203", "jn_lh203")
        connect("door_lh202", "jn_lh202")
        connect("door_lh201", "jn_lh201")
        connect("door_library", "jn_lh201")
        connect("door_lounge", "jn_lh201")

        // SOUTH CORRIDOR SEGMENTS
        connect("jn_lh204", "jn_lh203")
        connect("jn_lh203", "jn_lh202")
        connect("jn_lh202", "jn_lh201")
        connect("jn_lh201", "jn_top_stair")

        // CROSS-CORRIDORS
        connect("jn_lh204", "jn_top_9")
        connect("jn_lh203", "jn_top_15")
        connect("jn_lh202", "jn_top_245")
        connect("jn_lh201", "jn_top_stair")
    }

    private val adjacencyList = edges.groupBy { it.fromId }

    fun resolveLocationId(query: String): String {
        val q = query.lowercase().trim()
        val match = userLocations.firstOrNull { it.id.lowercase() == q || it.name.lowercase() == q }
            ?: userLocations.firstOrNull { q.contains(it.id.lowercase()) || q.contains(it.name.lowercase()) }
        if (match != null) return match.id

        return when {
            q.contains("201") -> "LH-201"
            q.contains("202") -> "LH-202"
            q.contains("203") -> "LH-203"
            q.contains("204") -> "LH-204"
            q.contains("205") -> "LH-205"
            q.contains("206") -> "LH-206"
            q.contains("207") -> "LH-207"
            q.contains("208") -> "L-208"
            q.contains("209") -> "L-209"
            q.contains("210") -> "L-210"
            q.contains("211") -> "L-211"
            q.contains("212") -> "L-212"
            q.contains("213") -> "L-213"
            q.contains("lounge") -> "Student Lounge"
            q.contains("library") -> "Library"
            q.contains("staff") -> "Staff Room"
            q.contains("washroom") || q.contains("toilet") -> "Washroom"
            q.contains("balcony") -> "Balcony"
            q.contains("lift") || q.contains("elevator") -> "Lift"
            q.contains("stairs") -> "Stairs"
            else -> query
        }
    }

    private fun resolveNodeId(id: String): String {
        if (nodesById.containsKey(id)) return id
        val normalized = "door_" + id.lowercase().replace("-", "")
        if (nodesById.containsKey(normalized)) return normalized
        return resolveLocationId(id)
    }

    fun calculateShortestPath(startId: String, destId: String): RouteResult? {
        val resolvedStart = resolveNodeId(startId)
        val resolvedDest = resolveNodeId(destId)

        val startNode = nodesById[resolvedStart] ?: return null
        val destNode  = nodesById[resolvedDest]  ?: return null
        if (resolvedStart == resolvedDest) return RouteResult(startNode, destNode, 0f, listOf(startNode),
            listOf(RouteStep("You are already at ${destNode.name}.", 0f, 0f, destNode.name)))

        val dist     = mutableMapOf<String, Float>().withDefault { Float.POSITIVE_INFINITY }
        val prevEdge = mutableMapOf<String, MapEdge>()
        val pq       = PriorityQueue<Pair<String, Float>>(compareBy { it.second })
        dist[resolvedStart] = 0f
        pq.add(resolvedStart to 0f)

        while (pq.isNotEmpty()) {
            val (curId, curDist) = pq.poll() ?: break
            if (curDist > dist.getValue(curId)) continue
            if (curId == resolvedDest) break
            for (edge in adjacencyList[curId] ?: emptyList()) {
                val nd = curDist + edge.distanceMeters
                if (nd < dist.getValue(edge.toId)) {
                    dist[edge.toId] = nd; prevEdge[edge.toId] = edge; pq.add(edge.toId to nd)
                }
            }
        }
        if (!prevEdge.containsKey(resolvedDest)) return null

        val rawEdgePath = mutableListOf<MapEdge>()
        var cur = resolvedDest
        while (cur != resolvedStart) { val e = prevEdge[cur] ?: break; rawEdgePath.add(0, e); cur = e.fromId }

        // PATH SIMPLIFICATION: Merge consecutive collinear corridor edges (heading difference <= 15°)
        val simplifiedEdges = simplifyEdgePath(rawEdgePath)

        val pathNodes = mutableListOf(startNode)
        for (e in simplifiedEdges) nodesById[e.toId]?.let { pathNodes.add(it) }

        return RouteResult(startNode, destNode, dist.getValue(resolvedDest), pathNodes,
            generateStepsFromSimplified(simplifiedEdges, destNode.name, startNode.name))
    }

    private fun simplifyEdgePath(rawEdgePath: List<MapEdge>): List<MapEdge> {
        if (rawEdgePath.isEmpty()) return emptyList()
        val validSegments = rawEdgePath.filter { it.distanceMeters >= 0.05f }
        if (validSegments.isEmpty()) return emptyList()

        val simplified = mutableListOf<MapEdge>()
        var curEdge = validSegments[0]

        for (i in 1 until validSegments.size) {
            val nextEdge = validSegments[i]
            val headingDiff = absAngleDiff(curEdge.headingDegrees, nextEdge.headingDegrees)
            if (headingDiff <= 15f) {
                val mergedDist = curEdge.distanceMeters + nextEdge.distanceMeters
                val mergedDesc = if (curEdge.description.isNotEmpty()) curEdge.description else nextEdge.description
                curEdge = MapEdge(
                    fromId = curEdge.fromId,
                    toId = nextEdge.toId,
                    distanceMeters = mergedDist,
                    headingDegrees = curEdge.headingDegrees,
                    description = mergedDesc
                )
            } else {
                simplified.add(curEdge)
                curEdge = nextEdge
            }
        }
        simplified.add(curEdge)
        return simplified
    }

    private fun generateStepsFromSimplified(simplifiedEdges: List<MapEdge>, destinationName: String, startName: String): List<RouteStep> {
        if (simplifiedEdges.isEmpty()) return emptyList()

        val steps = mutableListOf<RouteStep>()
        for (i in simplifiedEdges.indices) {
            val edge = simplifiedEdges[i]
            val targetNode = nodesById[edge.toId]
            val targetName = targetNode?.name ?: edge.toId
            val isFinalApproach = (i == simplifiedEdges.size - 1)
            val instruction = if (i == 0) {
                "Exit $startName and walk straight for %.1f metres.".format(edge.distanceMeters)
            } else {
                val prevEdge = simplifiedEdges[i - 1]
                val turn = normalizeAngle(edge.headingDegrees - prevEdge.headingDegrees)
                val targetLabel = if (isFinalApproach) "$destinationName entrance" else targetName
                when {
                    turn in -30f..30f   -> "Continue straight for %.1f metres.".format(edge.distanceMeters)
                    turn in 30f..150f   -> "Turn right towards $targetLabel, then walk %.1f metres.".format(edge.distanceMeters)
                    turn in -150f..-30f -> "Turn left towards $targetLabel, then walk %.1f metres.".format(edge.distanceMeters)
                    else                -> "Turn around, then walk straight for %.1f metres.".format(edge.distanceMeters)
                }
            }
            steps.add(RouteStep(instruction, edge.distanceMeters, edge.headingDegrees, targetName))
        }
        steps.add(RouteStep("Enter $destinationName. You have reached your destination.", 0f, simplifiedEdges.lastOrNull()?.headingDegrees ?: 0f, destinationName))
        return steps
    }

    private fun absAngleDiff(a: Float, b: Float): Float {
        return abs(normalizeAngle(a - b))
    }

    private fun normalizeAngle(angle: Float): Float {
        var a = (angle % 360f + 360f) % 360f
        if (a > 180f) a -= 360f
        return a
    }
}