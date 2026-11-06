package com.eftv.android.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.data.SeriesParser
import com.eftv.android.data.WatchProgress
import com.eftv.android.databinding.ItemEpisodeBinding

/** Lista dos episodios de uma temporada. */
class EpisodeAdapter(
    private val onClick: (Channel) -> Unit,
) : RecyclerView.Adapter<EpisodeAdapter.Holder>() {

    private var items: List<Channel> = emptyList()

    fun submit(list: List<Channel>) {
        items = list
        notifyDataSetChanged()
    }

    /** Atualiza o "min restantes" sem recarregar a lista (ao voltar do player). */
    fun updateProgress(progress: Map<String, WatchProgress>) {
        if (items.isEmpty()) return
        items = items.map { episode ->
            val saved = progress[episode.url]
            episode.copy(
                progressMs = saved?.positionMs ?: 0L,
                durationMs = saved?.durationMs ?: 0L,
            )
        }
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = items.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder =
        Holder(ItemEpisodeBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(holder: Holder, position: Int) {
        holder.bind(items[position])
    }

    inner class Holder(
        private val binding: ItemEpisodeBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(episode: Channel) {
            val context = binding.root.context
            val number = episode.episode
            binding.episodeNumber.text = number.toString()

            val episodeTitle = SeriesParser.parse(episode.name)?.episodeTitle.orEmpty()
            binding.episodeTitle.text = episodeTitle.ifBlank {
                context.getString(R.string.series_episode_label, number)
            }

            binding.episodeProgress.isVisible = episode.hasProgress
            binding.episodeRemaining.isVisible = episode.hasProgress
            if (episode.hasProgress) {
                binding.episodeProgress.progress = (episode.progressFraction * 100).toInt()
                val remaining = ((episode.durationMs - episode.progressMs) / 60_000L)
                    .coerceAtLeast(0L)
                binding.episodeRemaining.text =
                    context.getString(R.string.vod_remaining_min, remaining.toInt())
            }

            binding.root.setOnClickListener { onClick(episode) }
        }
    }
}
