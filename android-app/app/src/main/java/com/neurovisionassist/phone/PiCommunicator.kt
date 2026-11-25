package com.neurovisionassist.phone

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

data class NavigationPayload(
    val type: String,
    val instruction: String? = null,
    val distanceMeters: Float = 0f,
    val remainingDistanceMeters: Float = 0f,
    val distanceWalkedStep: Float = 0f,
    val stepDistance: Float = 0f,
    val currentStep: Int = 1,
    val totalSteps: Int = 1,
    val currentNode: String = "",
    val nextNode: String = "",
    val heading: Float? = null,
    val expectedHeading: Float? = null,
    val timestamp: Long = System.currentTimeMillis(),
)

class PiCommunicator(
    private val scope: CoroutineScope,
    private val onConnectionStatusUpdate: (isConnected: Boolean, statusText: String, lastSent: String, lastResponse: String) -> Unit,
    private val onStartNavigationTriggered: (() -> Unit)? = null,
    private val onSetStartCallback: ((String) -> Unit)? = null,
    private val onSetDestinationCallback: ((String) -> Unit)? = null,
) {
    private val isConnectedAtomic = AtomicBoolean(false)
    private var lastHost: String = "10.67.114.127"
    private var lastPort: Int = 8765
    private var pollingJob: Job? = null

    // Route calculation state for incoming Pi commands
    private var currentStartId: String = "Student Lounge"
    private var currentDestId: String = "LH-206"

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    private val client = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(4, TimeUnit.SECONDS)
        .writeTimeout(4, TimeUnit.SECONDS)
        .build()

    fun testConnection(host: String, port: Int) {
        lastHost = host
        lastPort = port

        scope.launch(Dispatchers.IO) {
            val pingUrl = "http://$host:$port/ping"
            Log.d(TAG, "Testing Pi HTTP connection: GET $pingUrl")
            val request = Request.Builder().url(pingUrl).get().build()
            try {
                val response = client.newCall(request).execute()
                val respText = response.body?.string() ?: ""
                val isSuccess = response.isSuccessful
                Log.d(TAG, "Ping response from $pingUrl: HTTP ${response.code} - $respText")

                isConnectedAtomic.set(isSuccess)

                withContext(Dispatchers.Main) {
                    onConnectionStatusUpdate(
                        isSuccess,
                        if (isSuccess) "Connected" else "HTTP ${response.code}",
                        "GET $pingUrl",
                        respText.ifEmpty { "HTTP ${response.code}" },
                    )
                }

                if (isSuccess) {
                    startCmdPolling(host, port)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Ping failed to $pingUrl: ${e.message}")
                isConnectedAtomic.set(false)
                withContext(Dispatchers.Main) {
                    onConnectionStatusUpdate(
                        false,
                        "Disconnected (${e.message ?: "Failed"})",
                        "GET $pingUrl",
                        e.message ?: "Connection error",
                    )
                }
            }
        }
    }

    private fun startCmdPolling(host: String, port: Int) {
        synchronized(this) {
            pollingJob?.cancel()
            pollingJob = scope.launch(Dispatchers.IO) {
                val cmdUrl = "http://$host:$port/cmd"
                while (isActive && isConnectedAtomic.get()) {
                    try {
                        val request = Request.Builder().url(cmdUrl).get().build()
                        val response = client.newCall(request).execute()
                        if (response.isSuccessful) {
                            val bodyStr = response.body?.string() ?: ""
                            if (bodyStr.isNotEmpty()) {
                                handleIncomingPiCommand(host, port, bodyStr)
                            }
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Error polling /cmd from $cmdUrl: ${e.message}")
                    }
                    delay(1500L)
                }
            }
        }
    }

    private suspend fun handleIncomingPiCommand(host: String, port: Int, bodyStr: String) {
        try {
            val json = JSONObject(bodyStr)
            val commandId = json.optString("command_id", json.optString("id", ""))
            val type = json.optString("type", json.optString("command", "")).trim()
            if (type.isEmpty()) return

            Log.d(TAG, "Received Pi HTTP command [id=$commandId, type=$type]: $bodyStr")

            // Acknowledge command if commandId present
            if (commandId.isNotEmpty()) {
                acknowledgeCommand(host, port, commandId)
            }

            when (type) {
                "SET_ROUTE_INPUTS" -> {
                    val startVal = json.optString("start").trim()
                    val destVal = json.optString("destination").trim()
                    if (startVal.isNotEmpty()) {
                        currentStartId = resolveLocationId(startVal)
                        withContext(Dispatchers.Main) { onSetStartCallback?.invoke(currentStartId) }
                    }
                    if (destVal.isNotEmpty()) {
                        currentDestId = resolveLocationId(destVal)
                        withContext(Dispatchers.Main) { onSetDestinationCallback?.invoke(currentDestId) }
                    }
                }
                "SET_START" -> {
                    val startVal = json.optString("start").trim()
                    if (startVal.isNotEmpty()) {
                        currentStartId = resolveLocationId(startVal)
                        withContext(Dispatchers.Main) { onSetStartCallback?.invoke(currentStartId) }
                    }
                }
                "SET_DESTINATION" -> {
                    val destVal = json.optString("destination").trim()
                    if (destVal.isNotEmpty()) {
                        currentDestId = resolveLocationId(destVal)
                        withContext(Dispatchers.Main) { onSetDestinationCallback?.invoke(currentDestId) }
                    }
                }
                "CALCULATE_ROUTE" -> {
                    Log.d(TAG, "Processing CALCULATE_ROUTE from Pi: $currentStartId -> $currentDestId")
                    val routeResult = IndoorMapRepository.calculateShortestPath(currentStartId, currentDestId)
                    if (routeResult != null && routeResult.steps.isNotEmpty()) {
                        val routePayload = NavigationPayload(
                            type = "ROUTE_READY",
                            instruction = routeResult.steps.firstOrNull()?.instruction ?: "",
                            distanceMeters = routeResult.steps.firstOrNull()?.distanceMeters ?: 0f,
                            remainingDistanceMeters = routeResult.totalDistanceMeters,
                            stepDistance = routeResult.steps.firstOrNull()?.distanceMeters ?: 0f,
                            currentStep = 1,
                            totalSteps = routeResult.steps.size,
                            currentNode = routeResult.startNode.name,
                            nextNode = routeResult.steps.firstOrNull()?.targetNodeName ?: routeResult.destinationNode.name
                        )
                        sendNavigationEvent(host, port, routePayload)
                    }
                }
                "START_NAVIGATION" -> {
                    Log.d(TAG, "Pi START_NAVIGATION command received")
                    withContext(Dispatchers.Main) {
                        onStartNavigationTriggered?.invoke()
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling incoming Pi command: ${e.message}")
        }
    }

    private fun acknowledgeCommand(host: String, port: Int, commandId: String) {
        scope.launch(Dispatchers.IO) {
            val ackUrl = "http://$host:$port/cmd/ack"
            val ackJson = JSONObject().apply {
                put("command_id", commandId)
                put("status", "OK")
            }.toString()
            val request = Request.Builder()
                .url(ackUrl)
                .post(ackJson.toRequestBody(jsonMediaType))
                .build()
            try {
                client.newCall(request).execute()
                Log.d(TAG, "POST /cmd/ack acknowledged command_id $commandId")
            } catch (e: Exception) {
                Log.w(TAG, "Failed to POST /cmd/ack for command_id $commandId: ${e.message}")
            }
        }
    }

    private fun resolveLocationId(query: String): String {
        val q = query.lowercase().trim()
        val locations = IndoorMapRepository.userLocations
        val match = locations.firstOrNull { it.id.lowercase() == q || it.name.lowercase() == q }
            ?: locations.firstOrNull { q.contains(it.id.lowercase()) || q.contains(it.name.lowercase()) }
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

    fun sendNavigationEvent(
        host: String,
        port: Int,
        payload: NavigationPayload,
    ) {
        lastHost = host
        lastPort = port

        if (payload.type == "TEST_CONNECTION") {
            testConnection(host, port)
            return
        }

        scope.launch(Dispatchers.IO) {
            val navUrl = "http://$host:$port/nav"
            val navJsonObj = JSONObject().apply {
                put("type", payload.type)
                put("instruction", payload.instruction ?: "")
                put("distance", "%.2f".format(payload.distanceMeters).toDouble())
                put("distance_remaining", "%.2f".format(payload.remainingDistanceMeters).toDouble())
                put("distance_walked_step", "%.2f".format(payload.distanceWalkedStep).toDouble())
                put("step_distance", "%.2f".format(payload.stepDistance).toDouble())
                put("current_step", payload.currentStep)
                put("total_steps", payload.totalSteps)
                put("current_node", payload.currentNode)
                put("next_node", payload.nextNode)
                put("current_location", payload.currentNode)
                put("next_location", payload.nextNode)
                put("heading", payload.heading?.let { "%.1f".format(it).toDouble() } ?: 0.0)
                put("expected_heading", payload.expectedHeading?.let { "%.1f".format(it).toDouble() } ?: 0.0)
                put("timestamp", payload.timestamp)
            }
            val navJsonStr = navJsonObj.toString()
            val summaryText = payload.instruction ?: payload.type
            Log.d(TAG, "[PI-STREAM] Sending instruction: $summaryText (Step ${payload.currentStep}/${payload.totalSteps}, Dist: ${payload.distanceMeters}m)")
            Log.d(TAG, "Posting navigation payload to POST $navUrl [type=${payload.type}]: $navJsonStr")

            val request = Request.Builder()
                .url(navUrl)
                .post(navJsonStr.toRequestBody(jsonMediaType))
                .build()

            try {
                val response = client.newCall(request).execute()
                val respText = response.body?.string() ?: ""
                val isSuccess = response.isSuccessful
                Log.d(TAG, "Response from POST $navUrl: HTTP ${response.code} - $respText")

                isConnectedAtomic.set(isSuccess)
                if (isSuccess) {
                    Log.d(TAG, "[PI-STREAM] Pi response received. Event sent successfully.")
                }

                withContext(Dispatchers.Main) {
                    onConnectionStatusUpdate(
                        isSuccess,
                        if (isSuccess) "Connected" else "HTTP ${response.code}",
                        "POST $navUrl (${payload.type})",
                        respText.ifEmpty { "HTTP ${response.code}" },
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to POST $navUrl: ${e.message}")
                isConnectedAtomic.set(false)
                withContext(Dispatchers.Main) {
                    onConnectionStatusUpdate(
                        false,
                        "Disconnected (${e.message ?: "POST failed"})",
                        "POST $navUrl",
                        e.message ?: "Network error",
                    )
                }
            }
        }
    }

    companion object {
        private const val TAG = "PiCommunicator"
    }
}