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

/**
 * Atualizacao do APK dentro do proprio app.
 *
 * Antes o botao "Atualizar" abria o navegador: o cliente baixava o arquivo e
 * muitas vezes nao achava onde ele foi salvo (ou o navegador embutido nem
 * iniciava o download). Aqui o app baixa em segundo plano, mostra progresso e
 * abre o instalador do Android direto no arquivo, via FileProvider.
 *
 * O APK so pode ser instalado com a mesma assinatura da versao atual; o
 * proprio Android recusa qualquer arquivo trocado no caminho.
 */
object UpdateInstaller {

    private const val APK_MIME = "application/vnd.android.package-archive"
    private const val APK_FILE = "eftv-update.apk"

    /** Android 8+ exige autorizacao para instalar apps fora da loja. */
    fun canInstall(activity: Activity): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            activity.packageManager.canRequestPackageInstalls()

    /** Abre a tela do sistema para liberar "instalar apps desconhecidos". */
    fun requestInstallPermission(activity: Activity) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val intent = Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            Uri.parse("package:${activity.packageName}"),
        )
        runCatching { activity.startActivity(intent) }
            .onFailure { Timber.w(it, "Nao foi possivel abrir a tela de instalacao") }
    }

    /**
     * Baixa o APK para o cache do app.
     *
     * @param onProgress recebe 0..100, ou -1 quando o servidor nao informa o
     * tamanho total (a barra vira indeterminada).
     */
    suspend fun download(
        activity: Activity,
        apkUrl: String,
        onProgress: (Int) -> Unit,
    ): File = withContext(Dispatchers.IO) {
        val target = File(activity.cacheDir, APK_FILE)
        if (target.exists()) target.delete()

        val connection = URL(apkUrl).openConnection() as HttpURLConnection
        connection.connectTimeout = 30_000
        connection.readTimeout = 60_000
        connection.instanceFollowRedirects = true
        connection.setRequestProperty("Accept", "application/vnd.android.package-archive")
        connection.setRequestProperty("User-Agent", "EFTV-Android/${BuildConfig.VERSION_NAME}")

        try {
            val code = connection.responseCode
            if (code !in 200..299) error("O servidor respondeu HTTP $code ao baixar a atualizacao.")

            val total = connection.contentLengthLong
            var downloaded = 0L
            connection.inputStream.use { input ->
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
            connection.disconnect()
        }
    }

    /** Abre o instalador do Android apontando para o APK baixado. */
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
