plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
android {
    val apiStage = providers.gradleProperty("chronoflowApiStage").getOrElse("competition")
    require(apiStage in listOf("competition", "production"))
    val gateway = providers.gradleProperty("chronoflowGatewayUrl").getOrElse("")
    require(gateway.isEmpty() || (gateway.startsWith("https://") && gateway.none { it == '"' || it == '\\' || it.code < 32 || it.code == 127 }))
    namespace = "com.chronoflow.local"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.chronoflow.local"
        minSdk = 26
        targetSdk = 35
        versionCode = 4
        versionName = "0.4.0"
        buildConfigField("boolean", "ALLOW_OFFICIAL_API", (apiStage == "competition").toString())
        buildConfigField("String", "OFFICIAL_GATEWAY_URL", "\"$gateway\"")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.02.00"))
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.1")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation(platform("androidx.compose:compose-bom:2025.02.00"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
