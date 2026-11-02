package com.eftv.android.data

import java.text.Normalizer
import java.util.Locale

private val DIACRITICS = Regex("\\p{M}+")

/** Minusculo, sem acento e sem espacos duplicados, para busca tolerante. */
fun String.normalizedForSearch(): String =
    Normalizer.normalize(lowercase(Locale.ROOT), Normalizer.Form.NFD)
        .replace(DIACRITICS, "")
        .replace(Regex("\\s+"), " ")
        .trim()
