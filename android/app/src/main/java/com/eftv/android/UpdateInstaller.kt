package com.eftv.android

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import timber.log.Timber
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

object UpdateInstaller {

    private const val APK_MIME = "application/vnd.android.package-archive"
    private const val APK_FILE = "eftv-update.apk"

    fun canInstall(activity: Activity): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            activity.packageManager.canRequestPackageInstalls()

    fun requestInstallPermission(activity: Activity) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${activity.packageName}"),
        )
        runCatching { activity.startActivity(intent) }
            .onFailure { Timber.w(it, "Nao foi possivel abrir a tela de instalacao") }
    }

    suspend fun download(
        activity: Activity,
        apkUrl: String,
        onProgress: (Int) -> Unit,
    ): File = withContext(Dispatchers.IO) {
        val target = File(activity.cacheDir, APK_FILE)
        if (target.exists()) target.delete()

        var currentUrl = apkUrl
        var connection: HttpURLConnection? = null
        for (redirect in 0..5) {
            val c = (URL(currentUrl).openConnection() as HttpURLConnection).apply {
                connectTimeout = 30_000
                readTimeout = 60_000
                instanceFollowRedirects = false
                setRequestProperty("Accept", "application/vnd.android.package-archive")
                setRequestProperty("User-Agent", "EFTV-Android/${BuildConfig.VERSION_NAME}")
            }
            val code = c.responseCode
            if (code in 300..399) {
                val loc = c.getHeaderField("Location")
                c.disconnect()
                if (loc.isNullOrBlank()) error("Redirecionamento sem Location")
                val next = URL(URL(currentUrl), loc).toString()
                if (!next.startsWith("https://", ignoreCase = true)) {
                    error("Redirecionamento inseguro: $next")
                }
                currentUrl = next
                continue
            }
            connection = c
            break
        }
        val conn = connection ?: error("Muitos redirecionamentos")

        try {
            val code = conn.responseCode
            if (code !in 200..299) error("O servidor respondeu HTTP $code ao baixar a atualizacao.")

            val total = conn.contentLengthLong
            var downloaded = 0L
            conn.inputStream.use { input ->
                target.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        downloaded += read
                        onProgress(
                            if (total > 0) {
                                ((downloaded * 100) / total).toInt().coerceIn(0, 100)
                            } else {
                                -1
                            }
                        )
                    }
                }
            }

            if (target.length() <= 0L) {
                target.delete()
                error("O arquivo baixado esta vazio.")
            }
            target
        } finally {
            conn.disconnect()
        }
    }

    fun install(activity: Activity, file: File) {
        val uri = FileProvider.getUriForFile(
            activity,
            "${activity.packageName}.fileprovider",
            file,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, APK_MIME)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        activity.startActivity(intent)
    }
}