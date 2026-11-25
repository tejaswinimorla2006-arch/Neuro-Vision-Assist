package com.neurovisionassist.phone

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

class AppHttpServer(
    private val port: Int = 8080,
    private val onNavigateRequested: (source: String, destination: String) -> Pair<RouteResult?, String>?,
) {
    private var serverSocket: ServerSocket? = null
    private var isRunning = false

    fun start() {
        if (isRunning) return
        thread(isDaemon = true, name = "AppHttpServerThread") {
            try {
                // Bind to 0.0.0.0 (all network interfaces / LAN wildcard) on port 8080
                serverSocket = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress("0.0.0.0", port))
                }
                isRunning = true
                Log.d(TAG, "SUCCESS: AppHttpServer successfully started and bound to 0.0.0.0:$port")

                while (isRunning) {
                    val clientSocket = try {
                        serverSocket?.accept()
                    } catch (e: Exception) {
                        if (isRunning) Log.w(TAG, "Accept error: ${e.message}")
                        null
                    } ?: break

                    thread(isDaemon = true, name = "AppHttpClientThread") {
                        handleClient(clientSocket)
                    }
                }
            } catch (e: Exception) {
                isRunning = false
                Log.e(TAG, "FATAL: AppHttpServer failed to start or bind to port $port: ${e.message}", e)
            }
        }
    }

    fun stop() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing AppHttpServer socket: ${e.message}")
        }
        serverSocket = null
        Log.d(TAG, "AppHttpServer stopped cleanly.")
    }

    private fun handleClient(socket: Socket) {
        try {
            socket.soTimeout = 5000
            val reader = BufferedReader(InputStreamReader(socket.inputStream, "UTF-8"))
            val writer = OutputStreamWriter(socket.outputStream, "UTF-8")

            val requestLine = reader.readLine() ?: ""
            Log.d(TAG, "HTTP Request line: $requestLine")

            var line: String?
            var contentLength = 0
            while (reader.readLine().also { line = it } != null) {
                if (line == null || line.trim().isEmpty()) break
                if (line.lowercase().startsWith("content-length:")) {
                    contentLength = line.substringAfter(":").trim().toIntOrNull() ?: 0
                }
            }

            val body = CharArray(contentLength)
            if (contentLength > 0) {
                reader.read(body, 0, contentLength)
            }
            val bodyString = String(body)
            Log.d(TAG, "HTTP Request body: $bodyString")

            val parts = requestLine.split(" ")
            val method = if (parts.isNotEmpty()) parts[0].uppercase() else "GET"
            val path = if (parts.size > 1) parts[1].split("?")[0] else "/"

            when {
                method == "GET" && path == "/ping" -> {
                    handlePing(writer)
                }
                method == "POST" && path == "/navigate" -> {
                    handleNavigate(bodyString, writer)
                }
                else -> {
                    val err = JSONObject().put("status", "error").put("message", "Not found or unsupported method/path").toString()
                    writeHttpResponse(writer, 404, err)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling HTTP client: ${e.message}", e)
            try {
                val writer = OutputStreamWriter(socket.outputStream, "UTF-8")
                val err = JSONObject().put("status", "error").put("message", e.message ?: "Internal server error").toString()
                writeHttpResponse(writer, 500, err)
            } catch (_: Exception) {}
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun handlePing(writer: OutputStreamWriter) {
        val resp = "pong"
        writer.write("HTTP/1.1 200 OK\r\n")
        writer.write("Content-Type: text/plain; charset=utf-8\r\n")
        writer.write("Content-Length: ${resp.length}\r\n")
        writer.write("Connection: close\r\n\r\n")
        writer.write(resp)
        writer.flush()
        Log.d(TAG, "GET /ping handled successfully (responded 'pong').")
    }

    private fun handleNavigate(bodyString: String, writer: OutputStreamWriter) {
        try {
            Log.d(TAG, "[API-LOG] Incoming POST /navigate request: body=$bodyString")
            val json = JSONObject(bodyString)
            val source = json.optString("source", json.optString("start", "")).trim()
            val destination = json.optString("destination", json.optString("dest", "")).trim()

            Log.d(TAG, "API /navigate parsed: source='$source', destination='$destination'")

            if (source.isEmpty() || destination.isEmpty()) {
                val errJson = JSONObject().put("status", "error").put("message", "Missing source or destination.").toString()
                Log.w(TAG, "[API-LOG] Route generation result: failed (missing source or destination)")
                writeHttpResponse(writer, 400, errJson)
                return
            }

            val navResult = onNavigateRequested(source, destination)
            val routeResult = navResult?.first
            val routeId = navResult?.second ?: "route_${System.currentTimeMillis()}"

            if (routeResult != null && routeResult.steps.isNotEmpty()) {
                Log.d(TAG, "[API-LOG] Route generation result: success=true, start=${routeResult.startNode.name}, dest=${routeResult.destinationNode.name}, totalDist=${routeResult.totalDistanceMeters}, stepsCount=${routeResult.steps.size}")

                val respObj = JSONObject().apply {
                    put("status", "success")
                    put("navigation_started", true)
                    put("route_id", routeId)
                    put("start", routeResult.startNode.name)
                    put("destination", routeResult.destinationNode.name)
                    put("source", routeResult.startNode.name)
                    put("total_distance_meters", "%.2f".format(routeResult.totalDistanceMeters).toDouble())
                    put("total_distance", "%.2f".format(routeResult.totalDistanceMeters).toDouble())
                    put("totalDistance", "%.2f".format(routeResult.totalDistanceMeters).toDouble())
                    
                    val stepsArray = JSONArray()
                    for ((idx, step) in routeResult.steps.withIndex()) {
                        stepsArray.put(JSONObject().apply {
                            put("step_number", idx + 1)
                            put("index", idx + 1)
                            put("instruction", step.instruction.replace("\n", " "))
                            put("distance", "%.2f".format(step.distanceMeters).toDouble())
                            put("distance_meters", "%.2f".format(step.distanceMeters).toDouble())
                            put("distanceMeters", "%.2f".format(step.distanceMeters).toDouble())
                            put("bearing", "%.1f".format(step.headingDegrees).toDouble())
                            put("heading", "%.1f".format(step.headingDegrees).toDouble())
                            put("headingDegrees", "%.1f".format(step.headingDegrees).toDouble())
                            put("targetNodeName", step.targetNodeName)
                            put("target_node_name", step.targetNodeName)
                        })
                    }
                    put("steps", stepsArray)
                }

                val jsonResponseStr = respObj.toString()
                Log.d(TAG, "[API-LOG] HTTP Response status: 200 OK | Exact JSON response: $jsonResponseStr")
                writeHttpResponse(writer, 200, jsonResponseStr)
                Log.d(TAG, "POST /navigate successfully completed for $source -> $destination (route_id=$routeId)")
            } else {
                Log.w(TAG, "[API-LOG] Route generation result: failed (no path found between '$source' and '$destination')")
                val errJson = JSONObject().apply {
                    put("status", "error")
                    put("message", "Could not calculate valid path between '$source' and '$destination'.")
                }.toString()
                writeHttpResponse(writer, 400, errJson)
            }
        } catch (e: Exception) {
            Log.e(TAG, "[API-LOG] Route generation result: exception error - ${e.message}", e)
            val errJson = JSONObject().apply {
                put("status", "error")
                put("message", "Invalid JSON format or processing error: ${e.message}")
            }.toString()
            writeHttpResponse(writer, 400, errJson)
        }
    }

    private fun writeHttpResponse(writer: OutputStreamWriter, statusCode: Int, jsonBody: String) {
        val statusText = when (statusCode) {
            200 -> "OK"
            400 -> "Bad Request"
            404 -> "Not Found"
            500 -> "Internal Server Error"
            else -> "OK"
        }
        writer.write("HTTP/1.1 $statusCode $statusText\r\n")
        writer.write("Content-Type: application/json; charset=utf-8\r\n")
        writer.write("Content-Length: ${jsonBody.length}\r\n")
        writer.write("Connection: close\r\n\r\n")
        writer.write(jsonBody)
        writer.flush()
    }

    companion object {
        private const val TAG = "AppHttpServer"
    }
}