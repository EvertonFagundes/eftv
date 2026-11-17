package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import coil.dispose
import coil.load
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.databinding.ItemContinueBinding

/**
 * Carrossel "Continuar assistindo" da home.
 *
 * Lista pequena e estável (no máximo uma dezena de itens), diferente do
 * [ChannelAdapter] que é paginado: aqui basta rebindar a lista inteira.
 */
class ContinueAdapter(
    private val onClick: (Channel) -> Unit,
) : RecyclerView.Adapter<ContinueAdapter.Holder>() {

    private val items = ArrayList<Channel>()

    fun submitList(newItems: List<Channel>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder =
        Holder(ItemContinueBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: Holder, position: Int) {
        holder.bind(items[position])
    }

    override fun onViewRecycled(holder: Holder) {
        super.onViewRecycled(holder)
        holder.cancelImage()
    }

    inner class Holder(
        private val binding: ItemContinueBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            binding.vodTitle.text = channel.name

            binding.vodPoster.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_movie)
                error(R.drawable.ic_movie)
                fallback(R.drawable.ic_movie)
                crossfade(true)
            }

            binding.vodProgress.isVisible = channel.hasProgress
            binding.remainingText.isVisible = channel.hasProgress
            if (channel.hasProgress) {
                binding.vodProgress.progress = (channel.progressFraction * 100).toInt()
                val remaining = ((channel.durationMs - channel.progressMs) / 60_000L)
                    .coerceAtLeast(0L)
                binding.remainingText.text = binding.root.context.getString(
                    R.string.vod_remaining_min,
                    remaining.toInt(),
                )
            }

            binding.root.setOnClickListener { onClick(channel) }
        }

        /** Cancela o download pendente para a capa antiga não cair em outro item. */
        fun cancelImage() {
            binding.vodPoster.dispose()
        }
    }
}
