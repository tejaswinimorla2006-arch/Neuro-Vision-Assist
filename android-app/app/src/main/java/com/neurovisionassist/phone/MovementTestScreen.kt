package com.neurovisionassist.phone

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.OutlinedButton
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

private val ink = Color(0xFF10191B)
private val panel = Color(0xFF1B282A)
private val accent = Color(0xFF63D9C4)
private val quiet = Color(0xFFA8B9B7)
private val warningColor = Color(0xFFFFC56E)

@Composable
fun MovementTestScreen(
    state: TrackingUiState,
    onStartTest: () -> Unit,
    onStopTest: () -> Unit,
    onResetTest: () -> Unit,
) {
    val movement = state.movementTest

    MaterialTheme(colorScheme = darkColorScheme(background = ink, surface = panel, primary = accent)) {
        Surface(modifier = Modifier.fillMaxSize(), color = ink) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Title & Live Status
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("NEURO VISION ASSIST", color = quiet, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        Text("Movement Test Mode", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                    }
                    Text(
                        text = if (movement.isTesting) "TESTING" else "STOPPED",
                        color = if (movement.isTesting) accent else quiet,
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
                    // Motion State Banner
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column {
                            Text("MOTION STATE", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            Text(
                                text = movement.motionState,
                                color = if (movement.motionState == "Walking") accent else Color.White,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        if (movement.isTesting && movement.lastStepLengthMeters > 0f) {
                            Text(
                                text = "Last step: ${"%.2f".format(movement.lastStepLengthMeters)} m",
                                color = quiet,
                                fontSize = 12.sp,
                            )
                        }
                    }

                    // Primary Metrics: Step Count & Estimated Distance
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        // Steps Box
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .background(panel, RoundedCornerShape(8.dp))
                                .padding(14.dp),
                        ) {
                            Text("STEP COUNT", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            Text(
                                text = "${movement.stepCount}",
                                color = Color.White,
                                fontSize = 32.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }

                        // Estimated Distance Box
                        Column(
                            modifier = Modifier
                                .weight(1f)
                                .background(panel, RoundedCornerShape(8.dp))
                                .padding(14.dp),
                        ) {
                            Text("ESTIMATED DISTANCE", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            Text(
                                text = "%.2f m".format(movement.estimatedDistanceMeters),
                                color = accent,
                                fontSize = 32.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }

                    // Compass Heading Card
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

                    // Sensor Raw Values
                    SensorReadout("Accelerometer | m/s^2", state.accelerometer)
                    SensorReadout("Gyroscope | rad/s", state.gyroscope)
                    SensorReadout("Magnetometer | uT", state.magnetometer)

                    // Disclaimer text as required
                    Text(
                        "Estimated distance is dynamically computed from motion signals. Position is relative to start and not globally accurate.",
                        color = quiet,
                        fontSize = 11.sp,
                    )
                }

                // Control Buttons: Start Test, Stop Test, Reset Test
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Button(
                            onClick = onStartTest,
                            enabled = !movement.isTesting,
                            modifier = Modifier
                                .weight(1f)
                                .height(50.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = ink),
                        ) {
                            Text("Start Test", fontWeight = FontWeight.Bold)
                        }

                        Button(
                            onClick = onStopTest,
                            enabled = movement.isTesting,
                            modifier = Modifier
                                .weight(1f)
                                .height(50.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF344548), contentColor = Color.White),
                        ) {
                            Text("Stop Test", fontWeight = FontWeight.Bold)
                        }
                    }

                    OutlinedButton(
                        onClick = onResetTest,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(44.dp),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = warningColor),
                    ) {
                        Text("Reset Test", fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
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