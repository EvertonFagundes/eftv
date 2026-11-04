package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.data.ChannelMode
import com.eftv.android.databinding.ItemCategoryBinding

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
        binding.root.text = items[position].label
        binding.root.isChecked = position == selectedPosition
        binding.root.setOnClickListener {
            // A posicao do bind pode ficar velha se a lista mudar; consulta a atual.
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

    class CategoryViewHolder(
        val binding: ItemCategoryBinding,
    ) : RecyclerView.ViewHolder(binding.root)

    companion object {
        const val ALL = "Todos"
    }
}
