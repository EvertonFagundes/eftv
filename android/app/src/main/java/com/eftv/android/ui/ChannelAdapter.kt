package com.eftv.android.ui

import android.animation.ValueAnimator
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.animation.AnimationUtils
import android.view.animation.LinearInterpolator
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.eftv.android.R
import com.eftv.android.data.Channel
import com.eftv.android.databinding.ItemChannelBinding
import kotlin.math.abs
import java.util.LinkedHashMap
import java.util.HashSet
import java.util.regex.Pattern

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
    private val shimmerAnimators = mutableMapOf<View, ValueAnimator>()
    private val pulseAnimators = mutableMapOf<View, android.view.animation.Animation>()

    // Cache de séries detectadas: nome base -> lista de episódios
    private val seriesCache = mutableMapOf<String, MutableList<Channel>>()

    fun reset(totalCount: Int) {
        pages.clear()
        seriesCache.clear()
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
        // Atualiza cache de séries
        detectSeries(items)
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

    override fun onViewRecycled(holder: ChannelViewHolder) {
        super.onViewRecycled(holder)
        holder.stopAnimations()
    }

    /** Detecta séries agrupando canais com nome base similar */
    private fun detectSeries(items: List<Channel>) {
        for (channel in items) {
            val baseName = extractSeriesBaseName(channel.name)
            if (baseName != channel.name) {
                seriesCache.getOrPut(baseName) { mutableListOf() }.add(channel)
            }
        }
    }

    /** Extrai nome base da série removendo números de episódio */
    private fun extractSeriesBaseName(name: String): String {
        // Padrões: "Serie Ep 1", "Serie E01", "Serie 1x01", "Serie S01E01", "Serie - 1", "Serie 01"
        val patterns = listOf(
            Regex("""\s+(?:Ep|Episodio|Episode|E)\s*\d+""", RegexOption.IGNORE_CASE),
            Regex("""\s+\d+x\d+"""),
            Regex("""\s+S\d+E\d+""", RegexOption.IGNORE_CASE),
            Regex("""\s+-\s*\d+$"""),
            Regex("""\s+\d{1,2}$"""),
            Regex("""\s+\(\d+\)$"""),
        )
        var base = name
        for (pattern in patterns) {
            base = pattern.replace(base, "").trim()
        }
        return base
    }

    /** Conta episódios de uma série */
    private fun getSeriesEpisodeCount(baseName: String): Int = seriesCache[baseName]?.size ?: 0

    inner class ChannelViewHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            stopAnimations()
            binding.root.alpha = 1f
            binding.channelName.text = channel.name
            binding.channelGroup.text = channel.group

            // Logo com Coil
            binding.channelLogo.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_tv)
                error(R.drawable.ic_tv)
                fallback(R.drawable.ic_tv)
                crossfade(true)
            }

            // ===== TIPO: AO VIVO vs SOB DEMANDA =====
            val isLive = isLiveStream(channel.url)
            val isSeries = isSeriesChannel(channel.name)

            // Badge AO VIVO pulsante no logo
            binding.liveBadge.apply {
                visibility = if (isLive) View.VISIBLE else View.GONE
                if (isLive) startPulseAnimation(this)
            }

            // Indicador tipo ao lado do nome: "AO VIVO" ou "SOB DEMANDA"
            binding.typeIndicator.apply {
                if (isLive) {
                    text = binding.root.context.getString(R.string.live_badge).replace("● ", "")
                    setBackgroundResource(R.drawable.bg_type_live)
                } else {
                    text = "SOB DEMANDA"
                    setBackgroundResource(R.drawable.bg_type_vod)
                }
                visibility = View.VISIBLE
            }

            // Badge qualidade (HD/4K/SD)
            val quality = detectQuality(channel.name, channel.url)
            binding.qualityBadge.apply {
                text = quality
                visibility = if (quality.isNotBlank()) View.VISIBLE else View.GONE
                setBackgroundResource(getQualityBackground(quality))
            }

            // Badge Série + contagem episódios
            if (isSeries) {
                val baseName = extractSeriesBaseName(channel.name)
                val epCount = getSeriesEpisodeCount(baseName)
                binding.seriesBadge.visibility = View.VISIBLE
                binding.episodeCount.apply {
                    text = "$epCount eps"
                    visibility = View.VISIBLE
                }
            } else {
                binding.seriesBadge.visibility = View.GONE
                binding.episodeCount.visibility = View.GONE
            }

            // Favorito
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
            binding.root.setOnLongClickListener {
                onToggleFavorite(channel)
                true
            }
        }

        fun bindPlaceholder() {
            binding.root.alpha = 0.6f
            binding.channelName.text = binding.root.context.getString(R.string.loading_channel)
            binding.channelGroup.text = ""
            binding.channelLogo.setImageResource(R.drawable.ic_tv)
            binding.liveBadge.visibility = View.GONE
            binding.qualityBadge.visibility = View.GONE
            binding.typeIndicator.visibility = View.GONE
            binding.seriesBadge.visibility = View.GONE
            binding.episodeCount.visibility = View.GONE
            binding.favoriteButton.visibility = View.INVISIBLE
            binding.root.setOnClickListener(null)
            binding.root.setOnLongClickListener(null)

            // Shimmer no placeholder
            startShimmer(binding.channelName)
            startShimmer(binding.channelGroup)
            startShimmer(binding.logoContainer)
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
                    val alpha = 0.3f + 0.4f * animation.animatedValue
                    view.alpha = alpha
                }
            }
            shimmerAnimators[view] = animator
            animator.start()
        }

        private fun stopAnimations() {
            shimmerAnimators.values.forEach { it.cancel() }
            shimmerAnimators.clear()
            pulseAnimators.values.forEach { view.startAnimation(android.view.animation.AnimationUtils.loadAnimation(view.context, android.R.anim.fade_out)) }
            pulseAnimators.clear()
            binding.channelName.alpha = 1f
            binding.channelGroup.alpha = 1f
            binding.logoContainer.alpha = 1f
            binding.typeIndicator.visibility = View.GONE
            binding.seriesBadge.visibility = View.GONE
            binding.episodeCount.visibility = View.GONE
        }

        /** Detecta se e stream ao vivo baseado na URL */
        private fun isLiveStream(url: String): Boolean {
            val lower = url.lowercase()
            return lower.contains(".m3u8") || lower.contains("live") || lower.contains("hls") || lower.contains(".ts")
        }

        /** Detecta se e serie baseada no nome */
        private fun isSeriesChannel(name: String): Boolean {
            val lower = name.lowercase()
            return lower.matches(Regex(""".*\s+(?:ep|episodio|episode|e)\s*\d+""", RegexOption.IGNORE_CASE)) ||
                   lower.matches(Regex(""".*\s+\d+x\d+""")) ||
                   lower.matches(Regex(""".*\s+s\d+e\d+""", RegexOption.IGNORE_CASE)) ||
                   lower.matches(Regex(""".*\s+-\s*\d+$""")) ||
                   lower.matches(Regex(""".*\s+\d{1,2}$""")) ||
                   lower.matches(Regex(""".*\s+\(\d+\)$"""))
        }

        /** Detecta qualidade baseada no nome/URL */
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
    }

    companion object {
        const val PAGE_SIZE = 100
        private const val KEEP_PAGES = 4
    }
}

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
    private val shimmerAnimators = mutableMapOf<View, ValueAnimator>()

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

    override fun onViewRecycled(holder: ChannelViewHolder) {
        super.onViewRecycled(holder)
        // Para shimmer no placeholder reciclado
        holder.stopShimmer()
    }

    inner class ChannelViewHolder(
        private val binding: ItemChannelBinding,
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(channel: Channel) {
            stopShimmer()
            binding.root.alpha = 1f
            binding.channelName.text = channel.name
            binding.channelGroup.text = channel.group

            // Logo com Coil
            binding.channelLogo.load(channel.logo.ifBlank { null }) {
                placeholder(R.drawable.ic_tv)
                error(R.drawable.ic_tv)
                fallback(R.drawable.ic_tv)
                crossfade(true)
            }

            // Badge AO VIVO
            val isLive = isLiveStream(channel.url)
            binding.liveBadge.visibility = if (isLive) View.VISIBLE else View.GONE

            // Badge qualidade (HD/4K/SD)
            val quality = detectQuality(channel.name, channel.url)
            binding.qualityBadge.apply {
                text = quality
                visibility = if (quality.isNotBlank()) View.VISIBLE else View.GONE
                setBackgroundResource(getQualityBackground(quality))
            }

            // Favorito
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
            binding.root.alpha = 0.6f
            binding.channelName.text = binding.root.context.getString(R.string.loading_channel)
            binding.channelGroup.text = ""
            binding.channelLogo.setImageResource(R.drawable.ic_tv)
            binding.liveBadge.visibility = View.GONE
            binding.qualityBadge.visibility = View.GONE
            binding.favoriteButton.visibility = View.INVISIBLE
            binding.root.setOnClickListener(null)
            binding.root.setOnLongClickListener(null)

            // Inicia shimmer no placeholder
            startShimmer(binding.channelName)
            startShimmer(binding.channelGroup)
            startShimmer(binding.logoContainer)
        }

        private fun startShimmer(view: View) {
            val animator = ValueAnimator.ofFloat(0f, 1f).apply {
                duration = 1200
                repeatCount = ValueAnimator.INFINITE
                repeatMode = ValueAnimator.RESTART
                interpolator = LinearInterpolator()
                addUpdateListener { animation ->
                    val alpha = 0.3f + 0.4f * animation.animatedValue
                    view.alpha = alpha
                }
            }
            shimmerAnimators[view] = animator
            animator.start()
        }

        private fun stopShimmer() {
            shimmerAnimators.values.forEach { it.cancel() }
            shimmerAnimators.clear()
            binding.channelName.alpha = 1f
            binding.channelGroup.alpha = 1f
            binding.logoContainer.alpha = 1f
        }

        /** Detecta se e stream ao vivo baseado na URL */
        private fun isLiveStream(url: String): Boolean {
            val lower = url.lowercase()
            return lower.contains(".m3u8") || lower.contains("live") || lower.contains("hls")
        }

        /** Detecta qualidade baseada no nome/URL */
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
    }

    companion object {
        const val PAGE_SIZE = 100
        private const val KEEP_PAGES = 4
    }
}
