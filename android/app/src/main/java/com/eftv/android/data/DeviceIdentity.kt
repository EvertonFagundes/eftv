package com.eftv.android.data

import android.content.Context
import android.os.Build
import android.provider.Settings
import java.security.MessageDigest
import java.util.UUID

/**
 * Identidade do aparelho para o vinculo da assinatura.
 *
 * Nao usa IMEI nem dados de hardware sensiveis. O id e derivado do
 * ANDROID_ID do app (que o proprio Android mantem estavel entre
 * desinstalar e reinstalar o aplicativo, sempre com a mesma assinatura).
 *
 * Antes era um UUID aleatorio gerado na primeira execucao: ao reinstalar o
 * app o id mudava e o aparelho ocupava uma nova vaga da assinatura, fazendo
 * o usuario ver "Assinatura em uso". Instalacoes antigas continuam usando o
 * id ja salvo, para nao perder o vinculo existente.
 */
class DeviceIdentity(context: Context) {

    private val appContext = context.applicationContext

    private val prefs = appContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    val id: String by lazy {
        prefs.getString(KEY_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: stableId().also { generated ->
                prefs.edit().putString(KEY_ID, generated).apply()
            }
    }

    val name: String by lazy {
        listOf(Build.MANUFACTURER, Build.MODEL)
            .filter { it.isNotBlank() }
            .joinToString(" ")
            .ifBlank { "Android" }
            .take(120)
    }

    /** Id derivado do ANDROID_ID; sobrevive a desinstalacao/reinstalacao. */
    private fun stableId(): String {
        val androidId = runCatching {
            Settings.Secure.getString(appContext.contentResolver, Settings.Secure.ANDROID_ID)
        }.getOrNull()

        val invalid = androidId.isNullOrBlank() ||
            androidId == "9774d56d682e549c" ||
            androidId == "unknown"
        if (invalid) return UUID.randomUUID().toString()

        val digest = MessageDigest.getInstance("SHA-256")
            .digest("eftv:$androidId".toByteArray(Charsets.UTF_8))
        val hex = digest.joinToString("") { "%02x".format(it) }
        return "eftv-${hex.take(32)}"
    }

    private companion object {
        const val PREFS = "eftv_device"
        const val KEY_ID = "device_id"
    }
}
