package com.neurovisionassist.phone

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
fun RoutePlannerScreen(
    state: TrackingUiState,
    onSelectStartLocation: (String) -> Unit,
    onSelectDestination: (String) -> Unit,
    onCalculateRoute: () -> Unit,
    onStartNavigation: () -> Unit,
    onPauseNavigation: () -> Unit,
    onResumeNavigation: () -> Unit,
    onCancelNavigation: () -> Unit,
) {
    val routeState = state.routePlanner
    val locations = IndoorMapRepository.userLocations

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
                        Text("Indoor Route Planner", color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.Bold)
                    }
                    Text(
                        text = if (routeState.isNavigating) (if (routeState.isPaused) "PAUSED" else "NAVIGATING") else "READY",
                        color = if (routeState.isNavigating) (if (routeState.isPaused) highlight else accent) else quiet,
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
                    // Pi Connection Status Banner
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(panel, RoundedCornerShape(8.dp))
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("RASPBERRY PI LINK", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            text = "Pi: ${routeState.piConnectionStatus}",
                            color = if (routeState.piConnectionStatus == "Connected") accent else highlight,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }

                    // Start Location Picker
                    LocationPicker(
                        label = "START LOCATION",
                        selectedLocationId = routeState.selectedStartNodeId,
                        options = locations,
                        onLocationSelected = onSelectStartLocation,
                    )

                    // Destination Picker
                    LocationPicker(
                        label = "DESTINATION",
                        selectedLocationId = routeState.selectedDestNodeId,
                        options = locations,
                        onLocationSelected = onSelectDestination,
                    )

                    // Calculate Route & Start Navigation Action Buttons
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Button(
                            onClick = onCalculateRoute,
                            modifier = Modifier
                                .weight(1f)
                                .height(48.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = ink),
                        ) {
                            Text("CALCULATE ROUTE", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }

                        Button(
                            onClick = onStartNavigation,
                            enabled = routeState.calculatedRoute != null && !routeState.isNavigating,
                            modifier = Modifier
                                .weight(1f)
                                .height(48.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF344548), contentColor = Color.White),
                        ) {
                            Text("START NAVIGATION", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }

                    // Navigation Control Buttons (PAUSE, RESUME, CANCEL)
                    if (routeState.isNavigating) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            if (!routeState.isPaused) {
                                Button(
                                    onClick = onPauseNavigation,
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(44.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = highlight, contentColor = ink),
                                ) {
                                    Text("PAUSE", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                }
                            } else {
                                Button(
                                    onClick = onResumeNavigation,
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(44.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = ink),
                                ) {
                                    Text("RESUME", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                                }
                            }

                            OutlinedButton(
                                onClick = onCancelNavigation,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(44.dp),
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFFF6B6B)),
                            ) {
                                Text("CANCEL", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            }
                        }
                    }

                    // Off Route Warning Banner
                    routeState.offRouteWarning?.let { warning ->
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(Color(0xFF5A2A1A), RoundedCornerShape(8.dp))
                                .padding(12.dp),
                        ) {
                            Text(
                                text = "OFF-ROUTE: $warning",
                                color = highlight,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }

                    // Route Summary & Next Instruction Box
                    routeState.calculatedRoute?.let { route ->
                        val currentIndex = routeState.currentStepIndex
                        val currentStep = route.steps.getOrNull(currentIndex) ?: route.steps.firstOrNull()
                        val nextStep = route.steps.getOrNull(currentIndex + 1)
                        val isFinalStep = currentIndex >= route.steps.size - 1

                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(panel, RoundedCornerShape(8.dp))
                                .padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text("ACTIVE ROUTE STATUS", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Column {
                                    Text("CURRENT WAYPOINT", color = quiet, fontSize = 10.sp)
                                    Text(
                                        text = currentStep?.targetNodeName ?: route.startNode.name,
                                        color = Color.White,
                                        fontSize = 15.sp,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                                Column(horizontalAlignment = Alignment.End) {
                                    Text("NEXT WAYPOINT", color = quiet, fontSize = 10.sp)
                                    Text(
                                        text = nextStep?.targetNodeName ?: route.destinationNode.name,
                                        color = accent,
                                        fontSize = 15.sp,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                Column {
                                    Text("REMAINING DISTANCE", color = quiet, fontSize = 10.sp)
                                    Text(
                                        text = "%.2f m".format(if (routeState.isNavigating) routeState.remainingRouteDistanceMeters else route.totalDistanceMeters),
                                        color = highlight,
                                        fontSize = 18.sp,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                                Column(horizontalAlignment = Alignment.End) {
                                    Text("CURRENT / EXPECTED HEADING", color = quiet, fontSize = 10.sp)
                                    val currentH = state.headingDegrees?.let { "%.1f".format((it + routeState.mapHeadingOffsetDegrees + 360f) % 360f) } ?: "--"
                                    val expectedH = currentStep?.headingDegrees?.let { "%.0f".format(it) } ?: "--"
                                    Text(
                                        text = "$currentH° / $expectedH°",
                                        color = Color.White,
                                        fontSize = 16.sp,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                            }

                            // Current Step Progress Bar / Badge
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    text = "STEP ${currentIndex + 1} OF ${route.steps.size}",
                                    color = accent,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                )
                                if (routeState.isNavigating && currentStep != null && currentStep.distanceMeters > 0f) {
                                    Text(
                                        text = "Edge progress: %.2f / %.2f m".format(
                                            routeState.distanceWalkedOnCurrentStep,
                                            currentStep.distanceMeters,
                                        ),
                                        color = quiet,
                                        fontSize = 11.sp,
                                    )
                                }
                            }

                            // Next Instruction Card
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .background(ink, RoundedCornerShape(6.dp))
                                    .padding(12.dp),
                            ) {
                                Text("NEXT INSTRUCTION", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                Text(
                                    text = if (isFinalStep) "Destination reached: ${route.destinationNode.name}." else currentStep?.instruction ?: "Proceed on route.",
                                    color = Color.White,
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                        }

                        // Full Turn-by-Turn Route Instructions List
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(panel, RoundedCornerShape(8.dp))
                                .padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Text("TURN-BY-TURN INSTRUCTIONS", color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)

                            route.steps.forEachIndexed { index, step ->
                                val isCurrent = index == currentIndex && routeState.isNavigating
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .background(if (isCurrent) Color(0xFF2A3C3F) else Color.Transparent, RoundedCornerShape(4.dp))
                                        .padding(vertical = 4.dp, horizontal = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(
                                        text = "${index + 1}.",
                                        color = if (isCurrent) accent else quiet,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.padding(end = 8.dp),
                                    )
                                    Text(
                                        text = step.instruction,
                                        color = if (isCurrent) Color.White else quiet,
                                        fontSize = 13.sp,
                                        fontWeight = if (isCurrent) FontWeight.Bold else FontWeight.Normal,
                                    )
                                }
                            }
                        }
                    } ?: run {
                        Text(
                            "Select a start location and destination, then tap 'CALCULATE ROUTE'.",
                            color = quiet,
                            fontSize = 12.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun LocationPicker(
    label: String,
    selectedLocationId: String,
    options: List<MapNode>,
    onLocationSelected: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxWidth()) {
        Text(label, color = quiet, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        Spacer(modifier = Modifier.height(4.dp))
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(panel, RoundedCornerShape(8.dp))
                .clickable { expanded = true }
                .padding(horizontal = 14.dp, vertical = 12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = selectedLocationId,
                    color = Color.White,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                )
                Icon(
                    imageVector = Icons.Default.ArrowDropDown,
                    contentDescription = "Select location",
                    tint = accent,
                )
            }

            DropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
                modifier = Modifier.background(panel),
            ) {
                options.forEach { node ->
                    DropdownMenuItem(
                        text = { Text(node.name, color = Color.White) },
                        onClick = {
                            onLocationSelected(node.id)
                            expanded = false
                        },
                    )
                }
            }
        }
    }
}