package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.databinding.ItemChannelBinding

class ChannelAdapter(
    private val onClick: (Channel) -> Unit,
) : RecyclerView.Adapter<ChannelAdapter.ChannelViewHolder>() {

    private val items = ArrayList<Channel>()

    fun submit(newItems: List<Channel>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = items.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChannelViewHolder {
        val binding = ItemChannelBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false,
        )
        return ChannelViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ChannelViewHolder, position: Int) {
        holder.bind(items[position])
    }

    inner class ChannelViewHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
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
    }
}
