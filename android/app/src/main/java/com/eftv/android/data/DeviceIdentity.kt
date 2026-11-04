package com.eftv.android.data

import android.content.Context
import android.os.Build
import java.util.UUID

/**
 * Identidade do aparelho para o vinculo da assinatura.
 *
 * E um UUID aleatorio gerado na primeira execucao (sem IMEI, Android ID ou
 * qualquer dado de hardware), guardado apenas neste aparelho.
 */
class DeviceIdentity(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    val id: String by lazy {
        prefs.getString(KEY_ID, null) ?: UUID.randomUUID().toString().also { generated ->
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

    private companion object {
        const val PREFS = "eftv_device"
        const val KEY_ID = "device_id"
    }
}
