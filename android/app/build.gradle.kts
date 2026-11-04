import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// A playlist licenciada fica em local.properties (ignorado pelo Git).
// O build gera PlaylistConfig.kt a partir dai; o repositorio nao guarda a URL.
// Em RELEASE: PLAYLIST_URL fica vazio (app usa backend). Em DEBUG: usa local.properties.
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

fun kotlinString(value: String): String = value
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")
    .replace("$", "\\$")

val playlistConfigDir = layout.buildDirectory.dir("generated/source/playlistConfig")

val generatePlaylistConfig by tasks.registering {
    // Só usa EFTV_PLAYLIST_URL em debug; release deixa vazio (backend obrigatório)
    val isDebug = project.findProperty("com.android.build.api.variant.BuildConfig.BUILD_TYPE")?.toString()?.lowercase() == "debug"
    val url = if (isDebug) localProperties.getProperty("EFTV_PLAYLIST_URL", "") else ""
    val userAgent = localProperties.getProperty("EFTV_PLAYLIST_USER_AGENT", "VLC/3.0.20 LibVLC/3.0.20")
    val outputDir = playlistConfigDir

    inputs.property("url", url)
    inputs.property("userAgent", userAgent)
    outputs.dir(outputDir)

    doLast {
        val packageDir = outputDir.get().asFile.resolve("com/eftv/android")
        packageDir.mkdirs()
        packageDir.resolve("PlaylistConfig.kt").writeText(
            """
            |package com.eftv.android
            |
            |/**
            | * Gerado automaticamente pelo build a partir de local.properties.
            | * Nao versionar este arquivo.
            | * Em release, PLAYLIST_URL vem vazio — app usa backend.
            | */
            |object PlaylistConfig {
            |    const val PLAYLIST_URL: String = "${kotlinString(url)}"
            |    const val USER_AGENT: String = "${kotlinString(userAgent)}"
            |}
            |""".trimMargin()
        )
    }
}

android {
    namespace = "com.eftv.android"
    compileSdk = 34

    sourceSets {
        getByName("main") {
            java.srcDir(playlistConfigDir)
        }
    }

    defaultConfig {
        applicationId = "com.eftv.android"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // URL do backend central. Pode ser trocada no build:
        //   ./gradlew assembleDebug -PEFTV_API_URL=https://api.eftv.com.br
        val apiUrl = (project.findProperty("EFTV_API_URL") as String?)
            ?: localProperties.getProperty("EFTV_API_URL")
            ?: "http://127.0.0.1:8000"
        buildConfigField("String", "API_BASE_URL", "\"$apiUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }

    packaging {
        resources.excludes.addAll(
            listOf(
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE",
                "META-INF/LICENSE.txt",
                "META-INF/NOTICE",
                "META-INF/NOTICE.txt",
            )
        )
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-ktx:1.8.2")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")

    // Player de video (HLS, MPEG-TS, MP4, DASH)
    implementation("androidx.media3:media3-exoplayer:1.3.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.3.1")
    implementation("androidx.media3:media3-ui:1.3.1")

    // Logos dos canais
    implementation("io.coil-kt:coil:2.6.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")

    // Logging
    implementation("com.jakewharton.timber:timber:5.0.1")

    testImplementation("junit:junit:4.13.2")
}

// Gera PlaylistConfig.kt sempre antes de compilar.
tasks.named("preBuild") {
    dependsOn(generatePlaylistConfig)
}
