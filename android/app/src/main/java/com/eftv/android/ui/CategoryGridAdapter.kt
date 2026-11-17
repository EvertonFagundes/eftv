package com.eftv.android.ui

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.R
import com.eftv.android.data.ChannelKind
import com.eftv.android.data.ChannelMode
import com.eftv.android.databinding.ItemCategoryCardBinding
import java.text.NumberFormat
import java.util.ArrayList

/**
 * Cartoes da tela de categorias: icone, nome e quantidade.
 *
 * Substitui o menu suspenso que empilhava dezenas de grupos sem contexto. A
 * quantidade e o que permite decidir: "Jogos do Dia" com 400 itens merece
 * entrar, um grupo com 0 nao aparece.
 */
class CategoryGridAdapter(
    private val kind: ChannelKind,
    private val onSelected: (Selection) -> Unit,
) : RecyclerView.Adapter<CategoryGridAdapter.CardViewHolder>() {

    /** O que a categoria representa para a tela principal. */
    data class Selection(
        val label: String,
        val mode: ChannelMode = ChannelMode.ALL,
        val group: String? = null,
    )

    data class Item(
        val selection: Selection,
        val count: Int,
        /** Icone do assunto; 0 usa o selo com a inicial como reserva. */
        val iconRes: Int = 0,
        val accentRes: Int,
        val containerRes: Int,
    )

    private val items = ArrayList<Item>()
    private val all = ArrayList<Item>()
    private var query: String = ""
    private var selectedMode: ChannelMode = ChannelMode.ALL
    private var selectedGroup: String? = null

    fun submit(list: List<Item>, mode: ChannelMode = ChannelMode.ALL, group: String? = null) {
        all.clear()
        all.addAll(list)
        selectedMode = mode
        selectedGroup = group
        applyFilter()
    }

    /** Posicao da categoria atual na lista exibida (para abrir ja nela). */
    fun positionOfSelected(): Int = items.indexOfFirst {
        it.selection.mode == selectedMode && it.selection.group == selectedGroup
    }

    fun filter(text: String) {
        query = text.trim()
        applyFilter()
    }

    private fun applyFilter() {
        items.clear()
        if (query.isBlank()) {
            items.addAll(all)
        } else {
            val needle = query.normalized()
            items.addAll(all.filter { it.selection.label.normalized().contains(needle) })
        }
        notifyDataSetChanged()
    }

    private fun String.normalized(): String = lowercase()
        .replace(Regex("[áàâãä]"), "a")
        .replace(Regex("[éèêë]"), "e")
        .replace(Regex("[íìîï]"), "i")
        .replace(Regex("[óòôõö]"), "o")
        .replace(Regex("[úùûü]"), "u")
        .replace("ç", "c")

    override fun getItemCount(): Int = items.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): CardViewHolder {
        val binding = ItemCategoryCardBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false,
        )
        return CardViewHolder(binding)
    }

    override fun onBindViewHolder(holder: CardViewHolder, position: Int) {
        val binding = holder.binding
        val item = items[position]
        val context = binding.root.context

        val accent = ContextCompat.getColor(context, item.accentRes)
        binding.categoryCard.setCardBackgroundColor(ContextCompat.getColor(context, item.containerRes))

        // Selo redondo: icone real do assunto ou, sem icone, a inicial do nome.
        binding.categoryBadge.backgroundTintList =
            ColorStateList.valueOf(ColorUtils.setAlphaComponent(accent, 45))
        if (item.iconRes != 0) {
            binding.categoryIcon.visibility = View.VISIBLE
            binding.categoryIcon.setImageResource(item.iconRes)
            binding.categoryIcon.setColorFilter(accent)
            binding.categoryInitial.visibility = View.GONE
        } else {
            binding.categoryIcon.visibility = View.GONE
            binding.categoryInitial.visibility = View.VISIBLE
            binding.categoryInitial.text = item.selection.label
                .firstOrNull { it.isLetterOrDigit() }
                ?.uppercase()
                ?: "•"
            binding.categoryInitial.setTextColor(accent)
        }

        binding.categoryLabel.text = item.selection.label

        val number = NumberFormat.getIntegerInstance()
        binding.categoryCount.text = context.getString(
            R.string.category_count,
            number.format(item.count),
            context.getString(kindNoun(item)),
        )
        binding.categoryCount.setTextColor(accent)

        val isSelected = item.selection.mode == selectedMode &&
            item.selection.group == selectedGroup
        val density = binding.root.resources.displayMetrics.density
        binding.categoryCard.strokeWidth = if (isSelected) (2 * density).toInt() else 0
        binding.categoryCard.strokeColor = accent

        // No controle remoto o foco e o cursor: sem borda o cliente se perde.
        binding.categoryCard.setOnFocusChangeListener { view, hasFocus ->
            if (hasFocus) {
                binding.categoryCard.strokeWidth = (2 * density).toInt()
                binding.categoryCard.strokeColor = accent
                view.animate().scaleX(1.04f).scaleY(1.04f).setDuration(120).start()
            } else {
                binding.categoryCard.strokeWidth = if (isSelected) (2 * density).toInt() else 0
                view.animate().scaleX(1f).scaleY(1f).setDuration(120).start()
            }
        }

        binding.root.setOnClickListener { onSelected(item.selection) }
    }

    private fun kindNoun(item: Item): Int = when {
        item.selection.mode == ChannelMode.FAVORITES -> R.string.category_noun_items
        item.selection.mode == ChannelMode.RECENTS -> R.string.category_noun_items
        kind == ChannelKind.MOVIE -> R.string.category_noun_movies
        kind == ChannelKind.SERIES -> R.string.category_noun_series
        else -> R.string.category_noun_channels
    }

    class CardViewHolder(val binding: ItemCategoryCardBinding) :
        RecyclerView.ViewHolder(binding.root)
}
