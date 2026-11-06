package com.eftv.android.ui

import android.animation.ValueAnimator
import android.content.Context
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.animation.AnimationUtils
import android.view.animation.LinearInterpolator
import android.widget.ImageButton
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import coil.dispose
import coil.load
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.data.ChannelKind
import com.eftv.android.data.WatchProgress
import com.eftv.android.databinding.ItemChannelBinding
import com.eftv.android.databinding.ItemVodBinding
import java.util.HashSet
import java.util.LinkedHashMap
import kotlin.math.abs

/**
 * Lista paginada: mantem na memoria apenas as paginas proximas da posicao
 * visivel. O total pode ter centenas de milhares de itens sem estourar o heap.
 *
 * O mesmo adapter desenha dois estilos:
 *  - Ao vivo: linha horizontal com logo, nome, grupo e qualidade.
 *  - Filmes/Series: grade com capa 16:9, selo, favorito e progresso.
 */
class ChannelAdapter(
    private val onClick: (Channel) -> Unit,
    private val onPageNeeded: (Int) -> Unit,
    private val onToggleFavorite: (Channel) -> Unit,
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    private val pages = LinkedHashMap<Int, List<Channel>>()
    private val favoriteUrls = HashSet<String>()
    private var total = 0
    private var kind: ChannelKind = ChannelKind.LIVE

    private val shimmerAnimators = mutableMapOf<View, ValueAnimator>()
    private val pulseAnimators = mutableMapOf<View, android.view.animation.Animation>()

    fun setKind(value: ChannelKind) {
        kind = value
    }

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

    /** URLs das paginas atualmente carregadas (para consultar progresso). */
    fun loadedUrls(): List<String> = pages.values.flatten().map { it.url }

    /** Atualiza o progresso das capas ja carregadas, sem recarregar a lista. */
    fun updateProgress(progress: Map<String, WatchProgress>) {
        if (pages.isEmpty()) return
        for ((page, items) in pages) {
            pages[page] = items.map { channel ->
                val saved = progress[channel.url]
                channel.copy(
                    progressMs = saved?.positionMs ?: 0L,
                    durationMs = saved?.durationMs ?: 0L,
                )
            }
        }
        notifyDataSetChanged()
    }

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

    override fun getItemViewType(position: Int): Int =
        if (kind == ChannelKind.LIVE) TYPE_LIVE else TYPE_VOD

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return if (viewType == TYPE_LIVE) {
            LiveHolder(ItemChannelBinding.inflate(inflater, parent, false))
        } else {
            VodHolder(ItemVodBinding.inflate(inflater, parent, false))
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        val channel = pages[position / PAGE_SIZE]?.getOrNull(position % PAGE_SIZE)
        if (channel == null) onPageNeeded(position / PAGE_SIZE)

        when (holder) {
            is LiveHolder -> if (channel == null) holder.bindPlaceholder() else holder.bind(channel)
            is VodHolder -> if (channel == null) holder.bindPlaceholder() else holder.bind(channel)
        }
    }

    override fun onViewRecycled(holder: RecyclerView.ViewHolder) {
        super.onViewRecycled(holder)
        when (holder) {
            is LiveHolder -> {
                holder.stopAnimations()
                holder.cancelImage()
            }
            is VodHolder -> {
                holder.stopAnimations()
                holder.cancelImage()
            }
        }
    }

    // ------------------------------------------------------------------
    // Ao vivo
    // ------------------------------------------------------------------

    inner class LiveHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            stopAnimations()
            binding.root.alpha = 1f
            binding.channelName.text = channel.name
            binding.channelGroup.text = channel.group

            binding.channelLogo.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_tv)
                error(R.drawable.ic_tv)
                fallback(R.drawable.ic_tv)
                crossfade(true)
            }

            // A aba já indica que é ao vivo; fica só o ponto pulsante no logo.
            binding.liveBadge.isVisible = true
            startPulseAnimation(binding.liveBadge)
            binding.typeIndicator.isVisible = false
            binding.seriesBadge.isVisible = false
            binding.episodeCount.isVisible = false

            val quality = detectQuality(channel.name, channel.url)
            binding.qualityBadge.apply {
                text = quality
                isVisible = quality.isNotBlank()
                setBackgroundResource(getQualityBackground(quality))
            }

            bindFavorite(binding.favoriteButton, channel)

            binding.root.setOnClickListener { onClick(channel) }
            binding.root.setOnLongClickListener {
                onToggleFavorite(channel)
                true
            }
        }

        fun bindPlaceholder() {
            stopAnimations()
            binding.root.alpha = 0.6f
            binding.channelName.text = binding.root.context.getString(R.string.loading_channel)
            binding.channelGroup.text = ""
            binding.channelLogo.dispose()
            binding.channelLogo.setImageResource(R.drawable.ic_tv)
            binding.liveBadge.isVisible = false
            binding.qualityBadge.isVisible = false
            binding.favoriteButton.visibility = View.INVISIBLE
            binding.root.setOnClickListener(null)
            binding.root.setOnLongClickListener(null)

            startShimmer(binding.channelName)
            startShimmer(binding.channelGroup)
            startShimmer(binding.logoContainer)
        }

        /** Cancela o download pendente para a capa antiga nao cair em outro item. */
        fun cancelImage() {
            binding.channelLogo.dispose()
        }

        fun stopAnimations() {
            cancelAnimations()
            binding.channelName.alpha = 1f
            binding.channelGroup.alpha = 1f
            binding.logoContainer.alpha = 1f
            binding.liveBadge.clearAnimation()
            binding.liveBadge.isVisible = false
            binding.typeIndicator.isVisible = false
            binding.seriesBadge.isVisible = false
            binding.episodeCount.isVisible = false
        }
    }

    // ------------------------------------------------------------------
    // Filmes / series
    // ------------------------------------------------------------------

    inner class VodHolder(
        private val binding: ItemVodBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            stopAnimations()
            binding.root.alpha = 1f
            binding.vodTitle.text = channel.name
            binding.vodGroup.text = if (channel.isSeriesCard) {
                seriesSummary(binding.root.context, channel)
            } else {
                channel.group
            }

            binding.vodPoster.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_movie)
                error(R.drawable.ic_movie)
                fallback(R.drawable.ic_movie)
                crossfade(true)
            }

            val isSeries = channel.kind == ChannelKind.SERIES
            binding.kindBadge.isVisible = true
            binding.kindBadge.text = binding.root.context.getString(
                if (isSeries) R.string.kind_series_badge else R.string.kind_movie_badge,
            )
            binding.kindBadge.setBackgroundResource(
                if (isSeries) R.drawable.bg_series else R.drawable.bg_type_vod,
            )

            val quality = if (channel.isSeriesCard) "" else detectQuality(channel.name, channel.url)
            binding.qualityBadge.apply {
                text = quality
                isVisible = quality.isNotBlank()
                setBackgroundResource(getQualityBackground(quality))
            }

            if (channel.isSeriesCard) {
                binding.favoriteButton.visibility = View.GONE
            } else {
                bindFavorite(binding.favoriteButton, channel)
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
            if (channel.isSeriesCard) {
                binding.root.setOnLongClickListener(null)
            } else {
                binding.root.setOnLongClickListener {
                    onToggleFavorite(channel)
                    true
                }
            }
        }

        fun bindPlaceholder() {
            stopAnimations()
            binding.root.alpha = 0.6f
            binding.vodTitle.text = binding.root.context.getString(R.string.loading_channel)
            binding.vodGroup.text = ""
            binding.vodPoster.dispose()
            binding.vodPoster.setImageResource(R.drawable.ic_movie)
            binding.kindBadge.isVisible = false
            binding.qualityBadge.isVisible = false
            binding.favoriteButton.visibility = View.INVISIBLE
            binding.vodProgress.isVisible = false
            binding.remainingText.isVisible = false
            binding.root.setOnClickListener(null)
            binding.root.setOnLongClickListener(null)

            startShimmer(binding.vodTitle)
            startShimmer(binding.vodGroup)
        }

        /** Cancela o download pendente para a capa antiga nao cair em outro item. */
        fun cancelImage() {
            binding.vodPoster.dispose()
        }

        fun stopAnimations() {
            cancelAnimations()
            binding.root.alpha = 1f
            binding.vodTitle.alpha = 1f
            binding.vodGroup.alpha = 1f
            binding.vodProgress.isVisible = false
            binding.remainingText.isVisible = false
        }
    }

    // ------------------------------------------------------------------
    // Comum
    // ------------------------------------------------------------------

    /** "5 temporadas · 120 episódios" no card da serie. */
    private fun seriesSummary(context: Context, channel: Channel): String {
        val resources = context.resources
        val seasons = resources.getQuantityString(
            R.plurals.series_seasons_count, channel.seriesSeasons, channel.seriesSeasons,
        )
        val episodes = resources.getQuantityString(
            R.plurals.series_episodes_count, channel.seriesEpisodes, channel.seriesEpisodes,
        )
        return "$seasons · $episodes"
    }

    private fun bindFavorite(button: ImageButton, channel: Channel) {
        val favorite = favoriteUrls.contains(channel.url)
        button.visibility = View.VISIBLE
        button.isSelected = favorite
        button.setImageResource(if (favorite) R.drawable.ic_star else R.drawable.ic_star_outline)
        button.contentDescription = button.context.getString(
            if (favorite) R.string.favorite_remove else R.string.favorite_add,
        )
        button.setOnClickListener { onToggleFavorite(channel) }
    }

    private fun startPulseAnimation(view: View) {
        val anim = AnimationUtils.loadAnimation(view.context, R.anim.live_pulse)
        view.startAnimation(anim)
        pulseAnimators[view] = anim
    }

    private fun startShimmer(view: View) {
        val animator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1200
            repeatCount = ValueAnimator.INFINITE
            repeatMode = ValueAnimator.RESTART
            interpolator = LinearInterpolator()
            addUpdateListener { animation ->
                val alpha = 0.3f + 0.4f * (animation.animatedValue as Float)
                view.alpha = alpha
            }
        }
        shimmerAnimators[view] = animator
        animator.start()
    }

    private fun cancelAnimations() {
        shimmerAnimators.values.forEach { it.cancel() }
        shimmerAnimators.clear()
        pulseAnimators.clear()
    }

    private fun detectQuality(name: String, url: String): String {
        val combined = (name + " " + url).lowercase()
        return when {
            combined.contains("4k") || combined.contains("2160p") -> "4K"
            combined.contains("1080") || combined.contains("full hd") || combined.contains("fhd") -> "1080p"
            combined.contains("720") || combined.contains("hd") -> "HD"
            combined.contains("480") || combined.contains("sd") -> "SD"
            else -> ""
        }
    }

    private fun getQualityBackground(quality: String): Int = when (quality.uppercase()) {
        "4K" -> R.drawable.bg_quality_4k
        "1080P" -> R.drawable.bg_quality_hd
        "HD" -> R.drawable.bg_quality_hd
        "SD" -> R.drawable.bg_quality_sd
        else -> R.drawable.bg_quality
    }

    companion object {
        const val PAGE_SIZE = 100
        private const val KEEP_PAGES = 4
        private const val TYPE_LIVE = 0
        private const val TYPE_VOD = 1
    }
}
