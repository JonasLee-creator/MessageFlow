plugins {
    id("com.android.application") version "8.7.3"
    id("org.jetbrains.kotlin.android") version "2.1.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0"
    // Keep Chaquopy's runtime dependency configurations in :app. Declaring
    // its version in the root project makes IDE builds resolve a root-owned
    // configuration from a Kotlin task without the root project state lock.
    id("com.chaquo.python") version "17.1.0"
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
        versionCode = 5
        versionName = "0.5.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
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
    buildTypes.getByName("release") {
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
}

// Package exactly the production planner and frozen export, never datasets,
// training checkpoints, experiments, API credentials or server code.
val modelRoot = rootProject.layout.projectDirectory.dir("../../model")
val embeddedPython = layout.buildDirectory.dir("generated/embeddedPython")
val embeddedAssets = layout.buildDirectory.dir("generated/embeddedAssets")
val syncEmbeddedPython by tasks.registering(Sync::class) {
    from(modelRoot) {
        include("evaluation/__init__.py", "evaluation/domain.py", "evaluation/planners.py",
            "evaluation/improved_planner.py", "evaluation/integrated_planner.py",
            "evaluation/metrics.py", "evaluation/plan_utils.py", "evaluation/predictor.py",
            "evaluation/model_inputs.py", "evaluation/config_integrated.json",
            "deployment/__init__.py", "deployment/planning.py", "deployment/android.py")
    }
    from(modelRoot.dir("src")) {
        include("chronoflow_model/__init__.py", "chronoflow_model/config.py",
            "chronoflow_model/records.py", "chronoflow_model/features.py")
    }
    into(embeddedPython)
}
val syncEmbeddedAssets by tasks.registering(Sync::class) {
    from(modelRoot.dir("deployment/artifacts")) {
        include("chronoflow_predictor.onnx", "feature_config.json", "model_metadata.json", "checksums.json")
    }
    into(embeddedAssets.map { it.dir("chronoflow") })
}
android.sourceSets.getByName("main").assets.srcDir(embeddedAssets)
chaquopy {
    defaultConfig {
        version = "3.12"
        providers.gradleProperty("chronoflowBuildPython").orNull?.let { buildPython(it) }
        pip { install("tzdata==2025.2") }
        // planning.py reads the frozen config relative to its module file.
        extractPackages("evaluation", "deployment")
    }
    sourceSets.getByName("main") { srcDir(embeddedPython.get().asFile) }
}
tasks.configureEach {
    if (name != "syncEmbeddedPython" && name.contains("Python")) dependsOn(syncEmbeddedPython)
    if (name != "syncEmbeddedAssets" && (name == "preBuild" || name.endsWith("Assets"))) dependsOn(syncEmbeddedAssets)
}
dependencies {
    implementation("androidx.core:core:1.13.1")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.23.2")
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
