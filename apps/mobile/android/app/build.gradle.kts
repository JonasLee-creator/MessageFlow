plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}
android {
    namespace = "com.chronoflow.app"
    compileSdk = 35
    ndkVersion = flutter.ndkVersion
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = JavaVersion.VERSION_17.toString() }
    defaultConfig {
        applicationId = "com.chronoflow.app"
        minSdk = 26
        targetSdk = 35
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }
    // Release signing must be supplied by the app owner. Debug APK is for local testing.
    buildTypes {
        getByName("release") { isMinifyEnabled = false }
    }
}
flutter { source = "../.." }
dependencies {
    implementation("androidx.work:work-runtime-ktx:2.10.1")
}
