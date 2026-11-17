package com.eftv.android.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat
import com.eftv.android.R

/**
 * Barra A-Z na lateral da lista.
 *
 * Com mais de 2 mil canais, arrastar ate a letra "S" e inviavel - era a
 * reclamacao principal de navegacao. Tocar (ou arrastar o dedo) na barra pula
 * direto para o primeiro item daquela letra.
 */
class AlphabetIndexView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0,
) : View(context, attrs, defStyleAttr) {

    var onLetterPicked: ((Char) -> Unit)? = null

    private val letters: List<Char> = listOf('#') + ('A'..'Z').toList()

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        color = ContextCompat.getColor(context, R.color.on_background)
    }

    /** Fundo arredondado: sem ele as letras pareciam soltas sobre os cartoes. */
    private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.background)
        alpha = 215
    }

    private var pressedIndex = -1

    init {
        isClickable = true
        isFocusable = false
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = (16 * resources.displayMetrics.density).toInt() + paddingLeft + paddingRight
        setMeasuredDimension(width, MeasureSpec.getSize(heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (height == 0) return

        val radius = 8 * resources.displayMetrics.density
        canvas.drawRoundRect(
            0f,
            0f,
            width.toFloat(),
            height.toFloat(),
            radius,
            radius,
            backgroundPaint,
        )

        val slot = height.toFloat() / letters.size
        paint.textSize = (slot * 0.58f).coerceIn(
            7 * resources.displayMetrics.density,
            11 * resources.displayMetrics.density,
        )
        val baselineOffset = paint.textSize / 3f

        letters.forEachIndexed { index, letter ->
            scriptTextColor(index == pressedIndex)
            canvas.drawText(
                letter.toString(),
                width / 2f,
                index * slot + slot / 2f + baselineOffset,
                paint,
            )
        }
        scriptTextColor(false)
    }

    private fun scriptTextColor(pressed: Boolean) {
        paint.color = ContextCompat.getColor(
            context,
            if (pressed) R.color.primary else R.color.on_background,
        )
        paint.alpha = if (pressed) 255 else 170
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        // A barra reage ao arrastar tambem: o cliente pode deslizar sobre as
        // letras para "varrer" a lista.
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_MOVE,
            -> {
                val index = indexForY(event.y)
                if (index != pressedIndex) {
                    pressedIndex = index
                    invalidate()
                    onLetterPicked?.invoke(letters[index])
                }
                return true
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                pressedIndex = -1
                invalidate()
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun indexForY(y: Float): Int {
        val slot = height.toFloat() / letters.size
        if (slot <= 0f) return 0
        return (y / slot).toInt().coerceIn(0, letters.lastIndex)
    }
}
