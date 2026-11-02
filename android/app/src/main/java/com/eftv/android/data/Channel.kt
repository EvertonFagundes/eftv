package com.eftv.android.data

data class Channel(
    val name: String,
    val group: String,
    val logo: String,
    val url: String,
    val tvgId: String = "",
    val userAgent: String? = null,
    val referer: String? = null,
) {
    /** Nome normalizado uma unica vez, para a busca nao recalcular a cada tecla. */
    val searchKey: String = name.normalizedForSearch()
}
