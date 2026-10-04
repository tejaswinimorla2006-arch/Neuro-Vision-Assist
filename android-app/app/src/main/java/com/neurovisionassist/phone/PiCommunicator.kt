package com.neurovisionassist.phone

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

data class NavigationPayload(
    val type: String,
    val instruction: String? = null,
    val distanceRemainingMeters: Float = 0f,
    val currentLocation: String = "",
    val nextLocation: String = "",
    val heading: Float? = null,
    val expectedHeading: Float? = null,
    val timestamp: Long = System.currentTimeMillis(),
)

class PiCommunicator(
    private val scope: CoroutineScope,
    private val onConnectionStatusUpdate: (isConnected: Boolean, statusText: String, lastSent: String, lastResponse: String) -> Unit,
) {
    private var isConnected = false

    init {
        disableSslVerificationForTesting()
    }

    fun sendNavigationEvent(
        host: String,
        port: Int,
        payload: NavigationPayload,
    ) {
        val json = JSONObject().apply {
            put("type", payload.type)
            put("instruction", payload.instruction ?: "")
            put("distance_remaining", "%.2f".format(payload.distanceRemainingMeters).toDouble())
            put("current_location", payload.currentLocation)
            put("next_location", payload.nextLocation)
            put("heading", payload.heading?.let { "%.1f".format(it).toDouble() } ?: 0.0)
            put("expected_heading", payload.expectedHeading?.let { "%.1f".format(it).toDouble() } ?: 0.0)
            put("timestamp", payload.timestamp)
        }

        val jsonString = json.toString()
        Log.d(TAG, "Sending event to Pi ($host:$port): $jsonString")

        scope.launch(Dispatchers.IO) {
            val (success, responseText) = postJsonToPi(host, port, jsonString)
            withContext(Dispatchers.Main) {
                isConnected = success
                onConnectionStatusUpdate(
                    success,
                    if (success) "Connected" else "Disconnected",
                    jsonString,
                    responseText,
                )
            }
        }
    }

    private fun postJsonToPi(host: String, port: Int, jsonPayload: String): Pair<Boolean, String> {
        // Try HTTP first, then HTTPS if HTTP fails
        val httpUrlStr = "http://$host:$port/nav"
        val httpsUrlStr = "https://$host:$port/nav"

        val resultHttp = tryPost(httpUrlStr, jsonPayload)
        if (resultHttp.first) return resultHttp

        val resultHttps = tryPost(httpsUrlStr, jsonPayload)
        if (resultHttps.first) return resultHttps

        return Pair(false, "Connection error: ${resultHttp.second}")
    }

    private fun tryPost(urlString: String, jsonPayload: String): Pair<Boolean, String> {
        var connection: HttpURLConnection? = null
        return try {
            val url = URL(urlString)
            connection = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                setRequestProperty("Accept", "application/json")
                connectTimeout = 3000
                readTimeout = 3000
                doOutput = true
                doInput = true
            }

            if (connection is HttpsURLConnection) {
                connection.hostnameVerifier = HostnameVerifier { _, _ -> true }
            }

            OutputStreamWriter(connection.outputStream, "UTF-8").use { writer ->
                writer.write(jsonPayload)
                writer.flush()
            }

            val statusCode = connection.responseCode
            val inputStream = if (statusCode in 200..299) connection.inputStream else connection.errorStream
            val responseText = BufferedReader(InputStreamReader(inputStream, "UTF-8")).use { it.readText() }

            if (statusCode in 200..299) {
                Pair(true, "HTTP $statusCode: $responseText")
            } else {
                Pair(false, "HTTP $statusCode: $responseText")
            }
        } catch (e: Exception) {
            Pair(false, e.message ?: e.javaClass.simpleName)
        } finally {
            connection?.disconnect()
        }
    }

    private fun disableSslVerificationForTesting() {
        try {
            val trustAllCerts = arrayOf<TrustManager>(
                object : X509TrustManager {
                    override fun getAcceptedIssuers(): Array<X509Certificate>? = null
                    override fun checkClientTrusted(certs: Array<X509Certificate>?, authType: String?) {}
                    override fun checkServerTrusted(certs: Array<X509Certificate>?, authType: String?) {}
                },
            )
            val sc = SSLContext.getInstance("SSL")
            sc.init(null, trustAllCerts, SecureRandom())
            HttpsURLConnection.setDefaultSSLSocketFactory(sc.socketFactory)
            HttpsURLConnection.setDefaultHostnameVerifier { _, _ -> true }
        } catch (e: Exception) {
            Log.w(TAG, "Could not disable SSL verification: ${e.message}")
        }
    }

    companion object {
        private const val TAG = "PiCommunicator"
    }
}