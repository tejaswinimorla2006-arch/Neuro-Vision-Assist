package com.neurovisionassist.phone

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val ink = Color(0xFF10191B)
private val panel = Color(0xFF1B282A)
private val accent = Color(0xFF63D9C4)
private val quiet = Color(0xFFA8B9B7)
private val highlight = Color(0xFFFFC56E)

@Composable
fun TestDebugScreen(
    state: TrackingUiState,
    onUpdatePiConfig: (String, Int) -> Unit,
    onTestPiConnection: () -> Unit,
) {
    val routeState = state.routePlanner
    var hostInput by remember(routeState.piHost) { mutableStateOf(routeState.piHost) }
    var portInput by remember(routeState.piPort) { mutableStateOf(routeState.piPort.toString()) }

    MaterialTheme(colorScheme = darkColorScheme(background = ink, surface = panel, primary = accent)) {
        Surface(modifier = Modifier.fillMaxSize(), color = ink) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Header
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("NEURO VISION ASSIST", color = quiet, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        Text("Test & Debug Mode", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                    }
                    Text(
                        text = routeState.piConnectionStatus.uppercase(),
                        color = if (routeState.piConnectionStatus == "Connected") accent else highlight,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }

                Column(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    // Raspberry Pi Config Card
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text("RASPBERRY PI WI-FI CONNECTION", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedTextField(
                                value = hostInput,
                                onValueChange = { hostInput = it },
                                label = { Text("Pi Host IP", color = quiet) },
                                singleLine = true,
                                modifier = Modifier.weight(2f),
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = accent,
                                    unfocusedBorderColor = quiet,
                                    focusedTextColor = Color.White,
                                    unfocusedTextColor = Color.White,
                                ),
                            )
                            OutlinedTextField(
                                value = portInput,
                                onValueChange = { portInput = it },
                                label = { Text("Port", color = quiet) },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedBorderColor = accent,
                                    unfocusedBorderColor = quiet,
                                    focusedTextColor = Color.White,
                                    unfocusedTextColor = Color.White,
                                ),
                            )
                        }

                        Button(
                            onClick = {
                                val port = portInput.toIntOrNull() ?: 8765
                                onUpdatePiConfig(hostInput.trim(), port)
                                onTestPiConnection()
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(44.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = ink),
                        ) {
                            Text("SAVE & TEST PI CONNECTION", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }

                    // Network Log Card
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text("PI NETWORK MESSAGES", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        Text("Last Sent Message:", color = quiet, fontSize = 10.sp)
                        Text(routeState.lastSentMessage, color = Color.White, fontSize = 11.sp)
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Last Pi Response / Status:", color = quiet, fontSize = 10.sp)
                        Text(routeState.lastPiResponse, color = accent, fontSize = 11.sp)
                    }

                    // Navigation State Debug Card
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text("NAVIGATION & GRAPH DEBUG", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        DebugRow("Start Node", routeState.selectedStartNodeId)
                        DebugRow("Target Destination", routeState.selectedDestNodeId)
                        DebugRow("Active Route Calculated", if (routeState.calculatedRoute != null) "YES (${routeState.calculatedRoute.pathNodes.size} nodes)" else "NO")
                        DebugRow("Current Waypoint Index", "Step ${routeState.currentStepIndex + 1} of ${routeState.calculatedRoute?.steps?.size ?: 0}")
                        DebugRow("Edge Distance Walked", "%.2f m".format(routeState.distanceWalkedOnCurrentStep))
                        DebugRow("Remaining Route Distance", "%.2f m".format(routeState.remainingRouteDistanceMeters))
                        DebugRow("Expected Heading", routeState.expectedHeadingDegrees?.let { "%.1f deg".format(it) } ?: "--")
                        DebugRow("Calibrated Compass Heading", state.headingDegrees?.let { "%.1f deg".format((it + routeState.mapHeadingOffsetDegrees + 360f) % 360f) } ?: "--")
                    }

                    // Motion & PDR Debug Card
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text("MOTION & SENSOR FUSION", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        DebugRow("Motion State", state.movementTest.motionState)
                        DebugRow("Step Count", "${state.movementTest.stepCount}")
                        DebugRow("Total Estimated Distance", "%.2f m".format(state.movementTest.estimatedDistanceMeters))
                        DebugRow("Last Step Length", "%.2f m".format(state.movementTest.lastStepLengthMeters))
                    }

                    // Raw Sensors
                    SensorReadout("Accelerometer | m/s^2", state.accelerometer)
                    SensorReadout("Gyroscope | rad/s", state.gyroscope)
                    SensorReadout("Magnetometer | uT", state.magnetometer)
                }
            }
        }
    }
}

@Composable
private fun DebugRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, color = quiet, fontSize = 12.sp)
        Text(value, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
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