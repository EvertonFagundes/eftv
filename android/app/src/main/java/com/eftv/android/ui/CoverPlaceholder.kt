package com.eftv.android.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.util.LruCache
import androidx.core.content.ContextCompat
import com.eftv.android.data.ChannelKind
import java.util.Locale
import kotlin.math.abs
import kotlin.math.min

/**
 * Capa gerada para quando o provedor nao entrega (ou entrega um link morto)
 * para o logo.
 *
 * Boa parte das listas M3U antigas aponta para `goo.gl`, `postimg` e outros
 * servicos que sairam do ar. Sem isso o card fica com um icone generico e a
 * tela inteira parece vazia. A capa local usa as iniciais do canal/serie e
 * uma cor estavel derivada do nome: nao depende de rede e identifica o item.
 *
 * O bitmap fica em cache; cada ImageView recebe um Drawable novo (um Drawable
 * nao pode ser compartilhado por varias views ao mesmo tempo).
 */
object CoverPlaceholder {

    private const val LIVE_WIDTH = 192
    private const val LIVE_HEIGHT = 108
    private const val VOD_WIDTH = 240
    private const val VOD_HEIGHT = 360

    private val cache = LruCache<String, Bitmap>(32)

    /** Palavras que nao ajudam a identificar o canal nas iniciais. */
    private val STOP_WORDS = setOf(
        "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos",
        "e", "em", "the", "of", "and", "el", "la", "los", "las",
    )

    private val TAGS = Regex("""\[[^\]]*\]""")
    private val PARENTHESES = Regex("""\([^)]*\)""")
    private val NON_WORD = Regex("""[^\p{L}\p{N} ]+""")
    private val SPACES = Regex("""\s+""")

    fun drawable(context: Context, name: String, kind: ChannelKind, fallbackRes: Int): Drawable {
        val initials = initials(name)
        if (initials.isBlank()) {
            return ContextCompat.getDrawable(context, fallbackRes)
                ?: throw IllegalStateException("Drawable de fallback ausente")
        }
        val width = if (kind == ChannelKind.LIVE) LIVE_WIDTH else VOD_WIDTH
        val height = if (kind == ChannelKind.LIVE) LIVE_HEIGHT else VOD_HEIGHT
        val key = "${kind.name}:${width}x$height:$initials"
        val bitmap = cache.get(key) ?: createBitmap(name, initials, kind, width, height).also {
            cache.put(key, it)
        }
        bitmap.density = context.resources.displayMetrics.densityDpi
        return BitmapDrawable(context.resources, bitmap).apply { isFilterBitmap = true }
    }

    /** Iniciais legiveis: "The Walking Dead" -> "WD", "GLOBO" -> "GL". */
    internal fun initials(name: String): String {
        val clean = name
            .replace(TAGS, " ")
            .replace(PARENTHESES, " ")
            .replace(NON_WORD, " ")
            .replace(SPACES, " ")
            .trim()
        if (clean.isBlank()) return ""

        val words = clean.split(' ')
            .filter { it.isNotBlank() && it.lowercase(Locale.ROOT) !in STOP_WORDS }
        if (words.isEmpty()) return ""
        if (words.size == 1) {
            return words[0].take(2).uppercase(Locale.ROOT)
        }
        return (words[0].take(1) + words[1].take(1)).uppercase(Locale.ROOT)
    }

    private fun createBitmap(
        name: String,
        initials: String,
        kind: ChannelKind,
        width: Int,
        height: Int,
    ): Bitmap {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val hue = (abs(name.hashCode()) % 360).toFloat()

        val background = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            shader = LinearGradient(
                0f,
                0f,
                width.toFloat(),
                height.toFloat(),
                Color.HSVToColor(floatArrayOf(hue, 0.58f, 0.56f)),
                Color.HSVToColor(floatArrayOf((hue + 28f) % 360f, 0.70f, 0.30f)),
                Shader.TileMode.CLAMP,
            )
        }
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), background)

        // Halo discreto para a capa nao ficar chapada.
        background.shader = null
        background.color = Color.argb(20, 255, 255, 255)
        canvas.drawCircle(width * 0.82f, height * 0.18f, width * 0.34f, background)

        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.argb(238, 255, 255, 255)
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            textSize = if (kind == ChannelKind.LIVE) {
                height * 0.42f
            } else {
                min(width, height) * 0.32f
            }
        }
        val metrics = text.fontMetrics
        val baseline = height / 2f - (metrics.ascent + metrics.descent) / 2f
        canvas.drawText(initials, width / 2f, baseline, text)
        return bitmap
    }
}
