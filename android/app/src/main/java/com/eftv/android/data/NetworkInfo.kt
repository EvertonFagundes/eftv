package com.eftv.android.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/**
 * Rotulo da rede ativa ("wifi", "movel", ...).
 *
 * Usado nos relatos de erro enviados ao backend: "nao funciona nos dados
 * moveis" sem dizer a rede nao ajuda a diagnosticar. O app tem permissao
 * ACCESS_NETWORK_STATE desde a primeira versao.
 */
object NetworkInfo {

    fun label(context: Context): String {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return "?"
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return "offline"
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "movel"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            else -> "outra"
        }
    }
}
