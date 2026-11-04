package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.View
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
    private val onToggleFavorite: (Channel) -> Unit,
) : RecyclerView.Adapter<ChannelAdapter.ChannelViewHolder>() {

    private val pages = LinkedHashMap<Int, List<Channel>>()
    private val favoriteUrls = HashSet<String>()
    private var total = 0

    fun reset(totalCount: Int) {
        pages.clear()
        total = totalCount
        notifyDataSetChanged()
    }

    fun setFavorites(urls: Set<String>) {
        favoriteUrls.clear()
        favoriteUrls.addAll(urls)
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

            val favorite = favoriteUrls.contains(channel.url)
            binding.favoriteButton.visibility = View.VISIBLE
            binding.favoriteButton.isSelected = favorite
            binding.favoriteButton.setImageResource(
                if (favorite) R.drawable.ic_star else R.drawable.ic_star_outline
            )
            binding.favoriteButton.contentDescription = binding.root.context.getString(
                if (favorite) R.string.favorite_remove else R.string.favorite_add,
            )
            binding.favoriteButton.setOnClickListener { onToggleFavorite(channel) }

            binding.root.setOnClickListener { onClick(channel) }
            // Em TV/controle remoto: OK abre, OK pressionado salva nos favoritos.
            binding.root.setOnLongClickListener {
                onToggleFavorite(channel)
                true
            }
        }

        fun bindPlaceholder() {
            binding.root.alpha = 0.45f
            binding.channelName.text = binding.root.context.getString(R.string.loading_channel)
            binding.channelGroup.text = ""
            binding.channelLogo.setImageResource(R.drawable.ic_tv)
            binding.favoriteButton.visibility = View.INVISIBLE
            binding.root.setOnClickListener(null)
            binding.root.setOnLongClickListener(null)
        }
    }

    companion object {
        const val PAGE_SIZE = 100
        private const val KEEP_PAGES = 4
    }
}
