package com.eftv.android.ui

import android.content.Context
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.R
import com.eftv.android.data.ChannelMode
import com.eftv.android.databinding.ItemCategoryBinding
import java.util.ArrayList

/**
 * Navegacao superior: Todos, Favoritos, Recentes e as categorias da playlist.
 */
class CategoryAdapter(
    private val onSelected: (Category) -> Unit,
) : RecyclerView.Adapter<CategoryAdapter.CategoryViewHolder>() {

    data class Category(
        val label: String,
        val mode: ChannelMode = ChannelMode.ALL,
        val group: String? = null,
    )

    private val items = ArrayList<Category>()
    private var selectedPosition = 0

    fun submit(groups: List<String>, favoritesLabel: String, recentsLabel: String) {
        items.clear()
        items.add(Category(ALL, ChannelMode.ALL))
        items.add(Category(favoritesLabel, ChannelMode.FAVORITES))
        items.add(Category(recentsLabel, ChannelMode.RECENTS))
        groups.forEach { title -> items.add(Category(title, ChannelMode.ALL, title)) }
        selectedPosition = 0
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = items.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): CategoryViewHolder {
        val binding = ItemCategoryBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false,
        )
        return CategoryViewHolder(binding)
    }

    override fun onBindViewHolder(holder: CategoryViewHolder, position: Int) {
        val binding = holder.binding
        val item = items[position]
        binding.root.text = item.label
        binding.root.isChecked = position == selectedPosition

        // Define ícone baseado no tipo
        binding.root.icon = getIconForCategory(binding.root.context, item)
        binding.root.setIconTintList(if (item.mode == ChannelMode.FAVORITES) {
            ContextCompat.getColorStateList(binding.root.context, R.color.chip_text)
        } else {
            ContextCompat.getColorStateList(binding.root.context, R.color.chip_text)
        })

        binding.root.setOnClickListener {
            val current = holder.bindingAdapterPosition
            if (current == RecyclerView.NO_POSITION || current == selectedPosition) {
                return@setOnClickListener
            }
            val previous = selectedPosition
            selectedPosition = current
            notifyItemChanged(previous)
            notifyItemChanged(current)
            onSelected(items[current])
        }
    }

    private fun getIconForCategory(context: Context, item: Category): Int = when (item.mode) {
        ChannelMode.ALL -> if (item.label == ALL) R.drawable.ic_tv else R.drawable.ic_category
        ChannelMode.FAVORITES -> R.drawable.ic_star
        ChannelMode.RECENTS -> R.drawable.ic_history
        else -> R.drawable.ic_category
    }

    class CategoryViewHolder(
        val binding: ItemCategoryBinding,
    ) : RecyclerView.ViewHolder(binding.root)

    companion object {
        const val ALL = "Todos"
    }
}
