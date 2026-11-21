import java.util.Properties
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// A playlist licenciada fica em local.properties (ignorado pelo Git).
// O build gera PlaylistConfig.kt por variante; o repositorio nao guarda a URL.
// Em release a URL fica vazia (o app usa somente o backend).
val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

// Assinatura de release. O arquivo android/keystore.properties e a chave .jks
// ficam fora do Git (veja .gitignore). Sem eles o build de release continua
// funcionando, mas gera APK nao assinado - use isso so para testes locais.
val keystoreProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

val releaseKeystoreFile: java.io.File? = keystoreProperties.getProperty("storeFile")
    ?.takeIf { it.isNotBlank() }
    ?.let { rootProject.file(it) }
    ?.takeIf { it.exists() }

// Modo local: o catalogo vem do servidor embutido (127.0.0.1:8124), sem
// login e sem backend na nuvem.
val localMode: Boolean =
    localProperties.getProperty("EFTV_LOCAL_MODE", "true").trim().toBoolean()

/**
 * Gera PlaylistConfig.kt em tempo de build.
 *
 * A URL licenciada nunca vai para o repositorio: em debug vem de
 * local.properties; em release fica vazia e o app usa apenas o backend.
 */
abstract class GeneratePlaylistConfigTask : DefaultTask() {
    @get:Input
    abstract val playlistUrl: Property<String>

    @get:Input
    abstract val userAgent: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun generate() {
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
            |    const val PLAYLIST_URL: String = "${escape(playlistUrl.get())}"
            |    const val USER_AGENT: String = "${escape(userAgent.get())}"
            |}
            |""".trimMargin()
        )
    }

    private fun escape(value: String): String = value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("$", "\\$")
}

androidComponents {
    onVariants { variant ->
        val isDebug = variant.buildType == "debug"
        val taskName = "generate${variant.name.replaceFirstChar { it.uppercase() }}PlaylistConfig"
        val task = tasks.register<GeneratePlaylistConfigTask>(taskName) {
            playlistUrl.set(
                if (isDebug) localProperties.getProperty("EFTV_PLAYLIST_URL", "") else ""
            )
            userAgent.set(
                localProperties.getProperty(
                    "EFTV_PLAYLIST_USER_AGENT",
                    "VLC/3.0.20 LibVLC/3.0.20",
                )
            )
        }
        variant.sources.java?.addGeneratedSourceDirectory(
            task,
            GeneratePlaylistConfigTask::outputDir,
        )
    }
}

// URL do backend central. Pode ser trocada no build:
//   ./gradlew assembleRelease -PEFTV_API_URL=https://api.eftv.com.br
// Tambem pode ficar em local.properties (ignorado pelo Git).
val configuredApiUrl: String =
    ((project.findProperty("EFTV_API_URL") as String?)
        ?: localProperties.getProperty("EFTV_API_URL", "")).trim()

// APK distribuido para clientes: nunca aponta para 127.0.0.1 nem para a LAN.
// Uma URL local em local.properties so vale para debug.
val productionApiUrl = "https://eftv.onrender.com"
val releaseApiUrl: String = configuredApiUrl.takeIf {
    it.startsWith("https://") && !it.contains("127.0.0.1") && !it.contains("localhost")
} ?: productionApiUrl

android {
    namespace = "com.eftv.android"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.eftv.android"
        minSdk = 24
        targetSdk = 34
        versionCode = 24
        versionName = "1.4.9"

        // Debug no emulador usa 127.0.0.1; num celular, configure local.properties
        // com EFTV_API_URL=http://IP-DO-PC:8000
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"${configuredApiUrl.ifBlank { "http://127.0.0.1:8000" }}\"",
        )
        buildConfigField("boolean", "LOCAL_MODE", localMode.toString())

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    signingConfigs {
        if (releaseKeystoreFile != null) {
            create("release") {
                storeFile = releaseKeystoreFile
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // R8 remove código morto e ofusca o app. Sem isso o APK levava
            // todas as classes das bibliotecas e ficava fácil de ler/alterar.
            // As regras de keep (Chaquopy, ZXing, app) estão em proguard-rules.pro.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")

            // Assinatura propria: permite atualizar o app sem desinstalar.
            if (releaseKeystoreFile != null) {
                signingConfig = signingConfigs.getByName("release")
            }

            // APK distribuido nao pode apontar para 127.0.0.1 nem para a LAN.
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")

            // Distribuicao sempre no modo backend: login, assinatura e catalogo
            // vem do servidor, nunca do banco local do aparelho.
            buildConfigField("boolean", "LOCAL_MODE", "false")
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

chaquopy {
    defaultConfig {
        version = "3.12"
    }
}

val repoRoot = rootProject.projectDir.parentFile
val syncEftvAssets = tasks.register<Copy>("syncEftvAssets") {
    from(repoRoot) {
        include("index.html", "canal.html", "manifest.webmanifest", "sw.js")
        include("assets/**", "embed/**", "api/**")
    }
    into(layout.projectDirectory.dir("src/main/assets/eftv"))
}
tasks.named("preBuild") {
    dependsOn(syncEftvAssets)
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-ktx:1.8.2")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.cardview:cardview:1.0.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.preference:preference:1.2.0")

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

    // QR code da assinatura na TV (gera o desenho; nao usa camera)
    implementation("com.google.zxing:core:3.5.3")

    testImplementation("junit:junit:4.13.2")
}
