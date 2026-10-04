package com.neurovisionassist.phone

import android.graphics.SurfaceTexture
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import com.google.ar.core.Coordinates2d
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.ar.core.exceptions.CameraNotAvailableException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

class ArCameraRenderer(
    private val session: Session,
    private val onFrame: (String, Float?, Float?, Float?) -> Unit,
    private val onError: (String) -> Unit,
) : GLSurfaceView.Renderer {
    private val vertices = floatBuffer(
        floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f),
    )
    private val textureCoordinates = floatBuffer(FloatArray(8))
    private val textureTransformInput = floatBuffer(
        floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f),
    )
    private var textureId = -1
    private var program = 0
    private var positionHandle = 0
    private var textureHandle = 0
    private var lastFrameReportedAt = 0L
    private var reportedError = false

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        try {
            textureId = createCameraTexture()
            program = createProgram(VERTEX_SHADER, FRAGMENT_SHADER)
            positionHandle = GLES20.glGetAttribLocation(program, "a_Position")
            textureHandle = GLES20.glGetAttribLocation(program, "a_TexCoord")
            session.setCameraTextureName(textureId)
        } catch (error: RuntimeException) {
            reportError("Could not initialize the ARCore camera preview: ${error.message ?: "unknown error"}")
        }
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        if (program == 0 || textureId < 0) return
        try {
            val frame = session.update()
            val camera = frame.camera
            val pose = camera.pose.takeIf { camera.trackingState == TrackingState.TRACKING }
            val now = System.nanoTime()
            if (now - lastFrameReportedAt >= REPORT_INTERVAL_NANOS) {
                lastFrameReportedAt = now
                onFrame(
                    camera.trackingState.name,
                    pose?.tx(),
                    pose?.ty(),
                    pose?.tz(),
                )
            }
            drawCamera(frame)
        } catch (error: CameraNotAvailableException) {
            reportError("ARCore camera became unavailable: ${error.message ?: "camera access failed"}")
        } catch (error: RuntimeException) {
            reportError("ARCore tracking failed: ${error.message ?: error.javaClass.simpleName}")
        }
    }

    private fun drawCamera(frame: com.google.ar.core.Frame) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        GLES20.glUseProgram(program)
        textureTransformInput.position(0)
        frame.transformCoordinates2d(
            Coordinates2d.OPENGL_NORMALIZED_DEVICE_COORDINATES,
            textureTransformInput,
            Coordinates2d.TEXTURE_NORMALIZED,
            textureCoordinates,
        )

        vertices.position(0)
        GLES20.glVertexAttribPointer(positionHandle, 2, GLES20.GL_FLOAT, false, 0, vertices)
        GLES20.glEnableVertexAttribArray(positionHandle)
        textureCoordinates.position(0)
        GLES20.glVertexAttribPointer(textureHandle, 2, GLES20.GL_FLOAT, false, 0, textureCoordinates)
        GLES20.glEnableVertexAttribArray(textureHandle)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textureId)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
    }

    private fun createCameraTexture(): Int {
        val textures = IntArray(1)
        GLES20.glGenTextures(1, textures, 0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, textures[0])
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        return textures[0]
    }

    private fun createProgram(vertexShader: String, fragmentShader: String): Int {
        val vertex = compileShader(GLES20.GL_VERTEX_SHADER, vertexShader)
        val fragment = compileShader(GLES20.GL_FRAGMENT_SHADER, fragmentShader)
        return GLES20.glCreateProgram().also { shaderProgram ->
            GLES20.glAttachShader(shaderProgram, vertex)
            GLES20.glAttachShader(shaderProgram, fragment)
            GLES20.glLinkProgram(shaderProgram)
            val linkStatus = IntArray(1)
            GLES20.glGetProgramiv(shaderProgram, GLES20.GL_LINK_STATUS, linkStatus, 0)
            if (linkStatus[0] == 0) {
                val message = GLES20.glGetProgramInfoLog(shaderProgram)
                GLES20.glDeleteProgram(shaderProgram)
                throw IllegalStateException("Camera preview shader could not link: $message")
            }
            GLES20.glDeleteShader(vertex)
            GLES20.glDeleteShader(fragment)
        }
    }

    private fun compileShader(type: Int, source: String): Int {
        val shader = GLES20.glCreateShader(type)
        GLES20.glShaderSource(shader, source)
        GLES20.glCompileShader(shader)
        val compileStatus = IntArray(1)
        GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, compileStatus, 0)
        if (compileStatus[0] == 0) {
            val message = GLES20.glGetShaderInfoLog(shader)
            GLES20.glDeleteShader(shader)
            throw IllegalStateException("Camera preview shader could not compile: $message")
        }
        return shader
    }

    private fun reportError(message: String) {
        if (!reportedError) {
            reportedError = true
            onError(message)
        }
    }

    private fun floatBuffer(values: FloatArray): FloatBuffer =
        ByteBuffer.allocateDirect(values.size * Float.SIZE_BYTES)
            .order(ByteOrder.nativeOrder())
            .asFloatBuffer()
            .apply { put(values); position(0) }

    private companion object {
        const val REPORT_INTERVAL_NANOS = 100_000_000L
        const val VERTEX_SHADER = """
            attribute vec4 a_Position;
            attribute vec2 a_TexCoord;
            varying vec2 v_TexCoord;
            void main() {
                gl_Position = a_Position;
                v_TexCoord = a_TexCoord;
            }
        """
        const val FRAGMENT_SHADER = """
            #extension GL_OES_EGL_image_external : require
            precision mediump float;
            uniform samplerExternalOES sTexture;
            varying vec2 v_TexCoord;
            void main() {
                gl_FragColor = texture2D(sTexture, v_TexCoord);
            }
        """
    }
}