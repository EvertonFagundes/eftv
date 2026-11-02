package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.databinding.ItemCategoryBinding

class CategoryAdapter(
    private val onSelected: (String) -> Unit,
) : RecyclerView.Adapter<CategoryAdapter.CategoryViewHolder>() {

    private val items = ArrayList<String>()
    private var selectedPosition = 0

    fun submit(groups: List<String>) {
        items.clear()
        items.add(ALL)
        items.addAll(groups)
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
        val label = items[position]
        holder.binding.root.text = label
        holder.binding.root.isChecked = position == selectedPosition
        holder.binding.root.setOnClickListener {
            if (position == selectedPosition) return@setOnClickListener
            val previous = selectedPosition
            selectedPosition = position
            notifyItemChanged(previous)
            notifyItemChanged(position)
            onSelected(label)
        }
    }

    class CategoryViewHolder(
        val binding: ItemCategoryBinding,
    ) : RecyclerView.ViewHolder(binding.root)

    companion object {
        const val ALL = "Todos"
    }
}
