package com.eftv.android

import android.app.Activity
import android.app.UiModeManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.view.View

/**
 * Ajustes de tela para TV box / Android TV.
 *
 * Muitas TVs e boxes aplicam *overscan* no HDMI: os ~5% das bordas somem,
 * cortando o titulo, o menu e o ultimo canal da lista. O Android TV nao
 * corrige isso sozinho porque depende da TV. Aqui aplicamos uma margem de
 * seguranca configuravel e deixamos o cliente escolher "nenhuma" quando a TV
 * nao corta nada.
 *
 * A margem e aplicada no conteudo da tela (nao no player, que e tela cheia) e
 * reaplicada no `onResume`, para valer assim que o cliente muda a opcao.
 */
object TvScreen {

    /** Mesmo arquivo de preferencias usado pelas configuracoes do app. */
    private const val PREFS_NAME = SettingsActivity.PREFS_NAME

    const val PREF_OVERSCAN_DP = "pref_tv_overscan"

    /** 24 dp: suficiente para a maioria dos cortes e discreto numa TV boa. */
    const val DEFAULT_OVERSCAN_DP = 24

    fun isTelevision(context: Context): Boolean {
        val pm = context.packageManager
        if (pm.hasSystemFeature(PackageManager.FEATURE_LEANBACK)) return true
        if (pm.hasSystemFeature(PackageManager.FEATURE_TELEVISION)) return true
        val uiMode = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        return uiMode?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION
    }

    /** Margem atual em dp; zero em celular/tablet. */
    fun overscanDp(context: Context): Int {
        if (!isTelevision(context)) return 0
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getInt(PREF_OVERSCAN_DP, DEFAULT_OVERSCAN_DP)
    }

    fun setOverscanDp(context: Context, dp: Int) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putInt(PREF_OVERSCAN_DP, dp.coerceAtLeast(0))
            .apply()
    }

    /** Aplica a margem no conteudo da atividade. Chamar no `onResume`. */
    fun apply(activity: Activity) {
        val content = activity.findViewById<View>(android.R.id.content) ?: return
        val px = (overscanDp(activity) * activity.resources.displayMetrics.density).toInt()
        // Nao retornar cedo quando px == 0: o cliente pode ter trocado de
        // "Pequena" para "Nenhuma" e a margem antiga precisa sair da tela.
        if (content.paddingLeft == px &&
            content.paddingTop == px &&
            content.paddingRight == px &&
            content.paddingBottom == px
        ) {
            return
        }
        content.setPadding(px, px, px, px)
    }
}
