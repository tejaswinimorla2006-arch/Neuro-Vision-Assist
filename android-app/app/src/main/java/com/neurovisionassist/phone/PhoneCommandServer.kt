package com.neurovisionassist.phone

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

class PhoneCommandServer(
    private val port: Int = 8888,
    private val onCommandReceived: (commandText: String) -> Unit,
    private val onNavigateRequested: (source: String, destination: String) -> RouteResult?,
) {
    private var serverSocket: ServerSocket? = null
    private var isRunning = false

    fun start() {
        if (isRunning) return
        isRunning = true
        thread(isDaemon = true, name = "PhoneCommandServerThread") {
            try {
                serverSocket = ServerSocket(port)
                Log.d(TAG, "PhoneCommandServer listening on port $port")

                while (isRunning) {
                    val clientSocket = serverSocket?.accept() ?: break
                    thread(isDaemon = true) {
                        handleClient(clientSocket)
                    }
                }
            } catch (e: Exception) {
                if (isRunning) {
                    Log.e(TAG, "Server socket error: ${e.message}")
                }
            }
        }
    }

    fun stop() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.w(TAG, "Error closing server socket: ${e.message}")
        }
        serverSocket = null
    }

    private fun handleClient(socket: Socket) {
        try {
            socket.soTimeout = 4000
            val reader = BufferedReader(InputStreamReader(socket.inputStream, "UTF-8"))
            val writer = OutputStreamWriter(socket.outputStream, "UTF-8")

            val requestLine = reader.readLine() ?: ""
            Log.d(TAG, "HTTP Request line: $requestLine")

            var line: String?
            var contentLength = 0
            while (reader.readLine().also { line = it } != null) {
                if (line == null || line!!.trim().isEmpty()) break
                if (line!!.lowercase().startsWith("content-length:")) {
                    contentLength = line!!.substringAfter(":").trim().toIntOrNull() ?: 0
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

            if (method == "POST" && path == "/navigate") {
                handleNavigateRequest(bodyString, writer)
            } else {
                handleGenericCommand(bodyString, writer)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling client request: ${e.message}")
            try {
                val writer = OutputStreamWriter(socket.outputStream, "UTF-8")
                val errJson = JSONObject().put("status", "error").put("message", e.message ?: "Server error").toString()
                writer.write("HTTP/1.1 500 Internal Server Error\r\n")
                writer.write("Content-Type: application/json\r\n")
                writer.write("Content-Length: ${errJson.length}\r\n")
                writer.write("Connection: close\r\n\r\n")
                writer.write(errJson)
                writer.flush()
            } catch (_: Exception) {}
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun handleNavigateRequest(bodyString: String, writer: OutputStreamWriter) {
        try {
            val json = JSONObject(bodyString)
            val source = json.optString("source", json.optString("start", "")).trim()
            val destination = json.optString("destination", json.optString("dest", "")).trim()

            Log.d(TAG, "API /navigate requested: source='$source', destination='$destination'")

            if (source.isEmpty() || destination.isEmpty()) {
                val errJson = JSONObject().apply {
                    put("status", "error")
                    put("message", "Missing 'source' and/or 'destination' parameters in JSON body.")
                }.toString()
                writeHttpResponse(writer, 400, errJson)
                return
            }

            val routeResult = onNavigateRequested(source, destination)
            if (routeResult != null && routeResult.steps.isNotEmpty()) {
                val respObj = JSONObject().apply {
                    put("status", "success")
                    put("source", routeResult.startNode.name)
                    put("destination", routeResult.destinationNode.name)
                    put("total_distance", "%.2f".format(routeResult.totalDistanceMeters).toDouble())
                    
                    val stepsArray = JSONArray()
                    for ((idx, step) in routeResult.steps.withIndex()) {
                        stepsArray.put(JSONObject().apply {
                            put("step_number", idx + 1)
                            put("instruction", step.instruction.replace("\n", " "))
                            put("distance", "%.2f".format(step.distanceMeters).toDouble())
                            put("targetNodeName", step.targetNodeName)
                        })
                    }
                    put("steps", stepsArray)
                }
                writeHttpResponse(writer, 200, respObj.toString())
                Log.d(TAG, "API /navigate successfully started navigation for $source -> $destination")
            } else {
                val errJson = JSONObject().apply {
                    put("status", "error")
                    put("message", "Could not calculate valid path between '$source' and '$destination'.")
                }.toString()
                writeHttpResponse(writer, 400, errJson)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error in handleNavigateRequest: ${e.message}")
            val errJson = JSONObject().apply {
                put("status", "error")
                put("message", "Invalid JSON format or processing error: ${e.message}")
            }.toString()
            writeHttpResponse(writer, 400, errJson)
        }
    }

    private fun handleGenericCommand(bodyString: String, writer: OutputStreamWriter) {
        var commandText = ""
        if (bodyString.isNotBlank()) {
            try {
                val json = JSONObject(bodyString)
                commandText = json.optString("command", bodyString)
            } catch (e: Exception) {
                commandText = bodyString
            }
        }

        if (commandText.isNotBlank()) {
            onCommandReceived(commandText)
        }

        val responseJson = JSONObject().apply {
            put("status", "accepted")
            put("received_command", commandText)
        }.toString()

        writeHttpResponse(writer, 200, responseJson)
    }

    private fun writeHttpResponse(writer: OutputStreamWriter, statusCode: Int, jsonBody: String) {
        val statusText = if (statusCode == 200) "OK" else "Bad Request"
        writer.write("HTTP/1.1 $statusCode $statusText\r\n")
        writer.write("Content-Type: application/json; charset=utf-8\r\n")
        writer.write("Content-Length: ${jsonBody.length}\r\n")
        writer.write("Connection: close\r\n\r\n")
        writer.write(jsonBody)
        writer.flush()
    }

    companion object {
        private const val TAG = "PhoneCommandServer"
    }
}