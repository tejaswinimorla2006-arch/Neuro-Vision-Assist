# Neuro Vision Assist Phone

Phase 1 phone-only tracking foundation. The app opens an ARCore camera session, reads the phone accelerometer, gyroscope, and magnetometer, calculates a magnetic compass heading, and shows ARCore tracking state and the camera pose relative to that AR session. These coordinates are not globally accurate indoor coordinates.

This app does not implement routes, maps, Pi communication, YOLO, Bluetooth routing, or navigation instructions. Raspberry Pi audio behavior is unchanged. The requested start announcement uses Android's Text-to-Speech API.

## Requirements

- Android Studio with Android SDK Platform 35 and Build Tools installed.
- JDK 17 (Android Studio's bundled JDK is suitable).
- Internet access for the first Gradle wrapper and dependency download.
- A physical ARCore-supported Android phone with Google Play Services for AR. An emulator is not a substitute for verifying phone sensors and camera tracking.

## Run

1. In Android Studio, choose **Open** and select this `android-app` directory.
2. Accept the Gradle sync and install any requested Android SDK components. Set the Gradle JDK to Android Studio's bundled JDK 17 if prompted.
3. Connect an ARCore-supported phone with USB debugging enabled; accept its USB debugging prompt.
4. Select the phone in Android Studio's device selector and run the `app` configuration.
5. Grant camera access, then tap **Start Tracking**. Allow Google Play Services for AR to install or update if prompted.

To build and install from a terminal with JDK 17, Android SDK Platform 35, and `adb` configured:

```sh
cd android-app
./gradlew :app:installDebug
```

Then launch **Neuro Vision Assist** from the phone's app launcher.

## Verify on a phone

1. With tracking started, point the top of the phone in a known direction and rotate it slowly. The magnetic heading should change; nearby magnets and metal can disturb it.
2. Walk a few steps forward and side-to-side while keeping the camera aimed at a textured indoor scene. ARCore should report `TRACKING`, and one or more session-relative X/Y/Z values should change in metres.
3. Cover the camera or move into a featureless/dark scene. ARCore may become `PAUSED` or otherwise lose tracking; coordinates should then display as unavailable rather than pretending to be a valid tracked pose.
4. Confirm the three sensor readouts change as the phone moves, and that Android speaks "Phone navigation tracking started." after a successful start.
5. Tap **Stop Tracking**. The camera closes and live values clear.

ARCore pose is relative to a temporary session origin, can drift, and resets with a new session. It is not a mapped floor coordinate or a globally accurate indoor position. Compass heading is magnetic, depends on sensor quality/calibration, and is not fused with the AR pose in this phase.