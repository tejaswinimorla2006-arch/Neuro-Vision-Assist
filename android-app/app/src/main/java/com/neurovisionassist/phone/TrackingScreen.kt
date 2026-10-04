package com.neurovisionassist.phone

import android.opengl.GLSurfaceView
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView

private val ink = Color(0xFF10191B)
private val panel = Color(0xFF1B282A)
private val accent = Color(0xFF63D9C4)
private val quiet = Color(0xFFA8B9B7)

@Composable
fun MainAppContainer(
    state: TrackingUiState,
    cameraView: GLSurfaceView?,
    onSelectTab: (Int) -> Unit,
    onStartTracking: () -> Unit,
    onStopTracking: () -> Unit,
    onStartMovementTest: () -> Unit,
    onStopMovementTest: () -> Unit,
    onResetMovementTest: () -> Unit,
    onSelectStartLocation: (String) -> Unit,
    onSelectDestination: (String) -> Unit,
    onCalculateRoute: () -> Unit,
    onStartNavigation: () -> Unit,
    onPauseNavigation: () -> Unit,
    onResumeNavigation: () -> Unit,
    onCancelNavigation: () -> Unit,
    onUpdatePiConfig: (String, Int) -> Unit,
    onTestPiConnection: () -> Unit,
) {
    MaterialTheme(colorScheme = darkColorScheme(background = ink, surface = panel, primary = accent)) {
        Surface(modifier = Modifier.fillMaxSize(), color = ink) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Top Navigation Bar (4 Tabs)
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .background(panel, RoundedCornerShape(8.dp))
                        .padding(3.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                ) {
                    TabItem(
                        title = "Overview",
                        selected = state.selectedTab == 0,
                        onClick = { onSelectTab(0) },
                        modifier = Modifier.weight(1f),
                    )
                    TabItem(
                        title = "Movement",
                        selected = state.selectedTab == 1,
                        onClick = { onSelectTab(1) },
                        modifier = Modifier.weight(1f),
                    )
                    TabItem(
                        title = "Route",
                        selected = state.selectedTab == 2,
                        onClick = { onSelectTab(2) },
                        modifier = Modifier.weight(1f),
                    )
                    TabItem(
                        title = "Debug/Pi",
                        selected = state.selectedTab == 3,
                        onClick = { onSelectTab(3) },
                        modifier = Modifier.weight(1f),
                    )
                }

                when (state.selectedTab) {
                    0 -> TrackingScreen(
                        state = state,
                        cameraView = cameraView,
                        onStart = onStartTracking,
                        onStop = onStopTracking,
                    )
                    1 -> MovementTestScreen(
                        state = state,
                        onStartTest = onStartMovementTest,
                        onStopTest = onStopMovementTest,
                        onResetTest = onResetMovementTest,
                    )
                    2 -> RoutePlannerScreen(
                        state = state,
                        onSelectStartLocation = onSelectStartLocation,
                        onSelectDestination = onSelectDestination,
                        onCalculateRoute = onCalculateRoute,
                        onStartNavigation = onStartNavigation,
                        onPauseNavigation = onPauseNavigation,
                        onResumeNavigation = onResumeNavigation,
                        onCancelNavigation = onCancelNavigation,
                    )
                    3 -> TestDebugScreen(
                        state = state,
                        onUpdatePiConfig = onUpdatePiConfig,
                        onTestPiConnection = onTestPiConnection,
                    )
                }
            }
        }
    }
}

@Composable
private fun TabItem(
    title: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(36.dp)
            .background(
                if (selected) accent else Color.Transparent,
                RoundedCornerShape(6.dp),
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = title,
            color = if (selected) ink else quiet,
            fontSize = 11.sp,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
        )
    }
}

@Composable
fun TrackingScreen(
    state: TrackingUiState,
    cameraView: GLSurfaceView?,
    onStart: () -> Unit,
    onStop: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text("NEURO VISION ASSIST", color = quiet, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                Text("Phone tracking", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.Bold)
            }
            Text(
                text = if (state.isTracking) "LIVE" else "STOPPED",
                color = if (state.isTracking) accent else quiet,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
            )
        }

        Box(
            modifier = Modifier
                .weight(1.1f)
                .fillMaxWidth()
                .background(Color.Black, RoundedCornerShape(8.dp)),
            contentAlignment = Alignment.Center,
        ) {
            if (state.isTracking && cameraView != null) {
                AndroidView(factory = { cameraView }, modifier = Modifier.fillMaxSize())
            } else {
                Text(
                    text = if (state.arTrackingState.startsWith("Unsupported")) "Sensor-only mode (No AR camera)" else "Camera preview is stopped",
                    color = quiet,
                    fontSize = 14.sp,
                )
            }
        }

        Column(
            modifier = Modifier
                .weight(1.5f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(panel, RoundedCornerShape(8.dp))
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Text("TRACKING STATUS", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Text(state.status, color = Color.White, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                Text("ARCore: ${state.arTrackingState}", color = accent, fontSize = 13.sp)
                Text(state.sensorStatus, color = quiet, fontSize = 12.sp)
                state.message?.let { Text(it, color = Color(0xFFFFC56E), fontSize = 12.sp) }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(panel, RoundedCornerShape(8.dp))
                    .padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("COMPASS HEADING", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    Text("Magnetic north", color = quiet, fontSize = 12.sp)
                }
                Text(
                    text = state.headingDegrees?.let { "%.1f deg".format(it) } ?: "--",
                    color = Color.White,
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(panel, RoundedCornerShape(8.dp))
                    .padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("AR POSE | SESSION-RELATIVE METRES", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Coordinate("X", state.poseX)
                    Coordinate("Y", state.poseY)
                    Coordinate("Z", state.poseZ)
                }
            }

            SensorReadout("Accelerometer | m/s^2", state.accelerometer)
            SensorReadout("Gyroscope | rad/s", state.gyroscope)
            SensorReadout("Magnetometer | uT", state.magnetometer)
            Text(
                "AR pose is local to this session. It is not a globally accurate indoor position.",
                color = quiet,
                fontSize = 11.sp,
            )
        }

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = onStart,
                enabled = !state.isTracking,
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = ink),
            ) {
                Text("Start Tracking", fontWeight = FontWeight.Bold)
            }
            Button(
                onClick = onStop,
                enabled = state.isTracking,
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF344548), contentColor = Color.White),
            ) {
                Text("Stop Tracking", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun Coordinate(label: String, value: Float?) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = quiet, fontSize = 12.sp)
        Text(value?.let { "%.3f".format(it) } ?: "--", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun SensorReadout(label: String, value: VectorReading?) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(panel, RoundedCornerShape(8.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = quiet, fontSize = 12.sp)
        Text(
            value?.let { "${it.x.fmt()}  ${it.y.fmt()}  ${it.z.fmt()}" } ?: "--",
            color = Color.White,
            fontSize = 11.sp,
        )
    }
}

private fun Float.fmt(): String = "%.1f".format(this)