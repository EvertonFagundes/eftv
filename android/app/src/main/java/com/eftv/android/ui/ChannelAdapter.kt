package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.databinding.ItemChannelBinding
import kotlin.math.abs

/**
 * Lista paginada: mantem na memoria apenas as paginas proximas da posicao
 * visivel. O total pode ter centenas de milhares de itens sem estourar o heap.
 */
class ChannelAdapter(
    private val onClick: (Channel) -> Unit,
    private val onPageNeeded: (Int) -> Unit,
) : RecyclerView.Adapter<ChannelAdapter.ChannelViewHolder>() {

    private val pages = LinkedHashMap<Int, List<Channel>>()
    private var total = 0

    fun reset(totalCount: Int) {
        pages.clear()
        total = totalCount
        notifyDataSetChanged()
    }

    fun putPage(page: Int, items: List<Channel>) {
        pages[page] = items
        val start = page * PAGE_SIZE
        val count = minOf(items.size, total - start).coerceAtLeast(0)
        if (count > 0) notifyItemRangeChanged(start, count)
    }

    fun isPageLoaded(page: Int): Boolean = pages.containsKey(page)

    /** Descarrega paginas distantes para manter o uso de memoria constante. */
    fun trim(centerPage: Int) {
        val iterator = pages.keys.iterator()
        while (iterator.hasNext()) {
            val page = iterator.next()
            if (abs(page - centerPage) <= KEEP_PAGES) continue

            iterator.remove()
            val start = page * PAGE_SIZE
            val count = minOf(PAGE_SIZE, total - start).coerceAtLeast(0)
            if (count > 0) notifyItemRangeChanged(start, count)
        }
    }

    override fun getItemCount(): Int = total

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChannelViewHolder {
        val binding = ItemChannelBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false,
        )
        return ChannelViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ChannelViewHolder, position: Int) {
        val channel = pages[position / PAGE_SIZE]?.getOrNull(position % PAGE_SIZE)
        if (channel == null) {
            holder.bindPlaceholder()
            onPageNeeded(position / PAGE_SIZE)
        } else {
            holder.bind(channel)
        }
    }

    inner class ChannelViewHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            binding.root.alpha = 1f
            binding.channelName.text = channel.name
            binding.channelGroup.text = channel.group

            binding.channelLogo.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_tv)
                error(R.drawable.ic_tv)
                fallback(R.drawable.ic_tv)
                crossfade(true)
            }

            binding.root.setOnClickListener { onClick(channel) }
        }

        fun bindPlaceholder() {
            binding.root.alpha = 0.45f
            binding.channelName.text = binding.root.context.getString(R.string.loading_channel)
            binding.channelGroup.text = ""
            binding.channelLogo.setImageResource(R.drawable.ic_tv)
            binding.root.setOnClickListener(null)
        }
    }

    companion object {
        const val PAGE_SIZE = 100
        private const val KEEP_PAGES = 4
    }
}
