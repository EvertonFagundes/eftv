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
 * Navegação superior por categorias: cartões profissionais com ícone e cor por categoria.
 *
 * Categorias organizadas:
 * - Todos, Favoritos, Recentes (sistema)
 * - Filmes e Séries (separados, com destaque)
 * - Infantil, Esportes, Notícias, Abertos, Documentários, Animes, Novelas,
 *   Religiosos, Música, Variedades, 24 Horas, Streaming, Adultos, Outros
 */
class CategoryAdapter(
    private val onSelected: (Category) -> Unit,
    private val context: Context,
) : RecyclerView.Adapter<CategoryAdapter.CategoryViewHolder>() {

    data class Category(
        val label: String,
        val mode: ChannelMode = ChannelMode.ALL,
        val group: String? = null,
        val iconRes: Int = R.drawable.ic_category,
        val colorRes: Int = R.color.cat_all,
        val colorContainerRes: Int = R.color.cat_all_container,
    )

    private val items = ArrayList<Category>()
    private var selectedPosition = 0

    /**
     * Monta a lista de categorias.
     * [groups] são os group-titles vindos da playlist (para categorias dinâmicas).
     * A categoria "Adultos" só é exibida se o usuário habilitar nas configurações
     * (acessível por toque longo no título da tela principal).
     */
    fun submit(
        groups: List<String>,
        favoritesLabel: String,
        recentsLabel: String,
    ) {
        items.clear()

        val adultEnabled = SettingsActivity.isAdultContentEnabled(context)

        // --- Sistema ---
        items.add(Category(
            label = ALL,
            mode = ChannelMode.ALL,
            iconRes = R.drawable.ic_tv,
            colorRes = R.color.cat_all,
            colorContainerRes = R.color.cat_all_container,
        ))
        items.add(Category(
            label = favoritesLabel,
            mode = ChannelMode.FAVORITES,
            iconRes = R.drawable.ic_star,
            colorRes = R.color.cat_religious,
            colorContainerRes = R.color.cat_religious_container,
        ))
        items.add(Category(
            label = recentsLabel,
            mode = ChannelMode.RECENTS,
            iconRes = R.drawable.ic_history,
            colorRes = R.color.cat_news,
            colorContainerRes = R.color.cat_news_container,
        ))

        // --- Categorias principais (fixas, profissionais) ---
        // Filmes e Séries são listados primeiro, separados e destacados
        items.add(Category(
            label = "Filmes",
            mode = ChannelMode.ALL,
            group = "Filmes",
            iconRes = R.drawable.ic_movie,
            colorRes = R.color.cat_movie,
            colorContainerRes = R.color.cat_movie_container,
        ))
        items.add(Category(
            label = "Séries",
            mode = ChannelMode.ALL,
            group = "Séries",
            iconRes = R.drawable.ic_series,
            colorRes = R.color.cat_series,
            colorContainerRes = R.color.cat_series_container,
        ))

        // Demais categorias organizadas
        items.add(Category(
            label = "Infantil",
            mode = ChannelMode.ALL,
            group = "Infantil",
            iconRes = R.drawable.ic_child_friendly,
            colorRes = R.color.cat_child,
            colorContainerRes = R.color.cat_child_container,
        ))
        items.add(Category(
            label = "Esportes",
            mode = ChannelMode.ALL,
            group = "Esportes",
            iconRes = R.drawable.ic_sports,
            colorRes = R.color.cat_sports,
            colorContainerRes = R.color.cat_sports_container,
        ))
        items.add(Category(
            label = "Notícias",
            mode = ChannelMode.ALL,
            group = "Notícias",
            iconRes = R.drawable.ic_news,
            colorRes = R.color.cat_news,
            colorContainerRes = R.color.cat_news_container,
        ))
        items.add(Category(
            label = "Abertos",
            mode = ChannelMode.ALL,
            group = "Abertos",
            iconRes = R.drawable.ic_tv,
            colorRes = R.color.cat_abertos,
            colorContainerRes = R.color.cat_abertos_container,
        ))
        items.add(Category(
            label = "Documentários",
            mode = ChannelMode.ALL,
            group = "Documentários",
            iconRes = R.drawable.ic_documentary,
            colorRes = R.color.cat_documentary,
            colorContainerRes = R.color.cat_documentary_container,
        ))
        items.add(Category(
            label = "Animes",
            mode = ChannelMode.ALL,
            group = "Animes",
            iconRes = R.drawable.ic_anime,
            colorRes = R.color.cat_anime,
            colorContainerRes = R.color.cat_anime_container,
        ))
        items.add(Category(
            label = "Novelas",
            mode = ChannelMode.ALL,
            group = "Novelas",
            iconRes = R.drawable.ic_novela,
            colorRes = R.color.cat_novela,
            colorContainerRes = R.color.cat_novela_container,
        ))
        items.add(Category(
            label = "Religiosos",
            mode = ChannelMode.ALL,
            group = "Religiosos",
            iconRes = R.drawable.ic_religious,
            colorRes = R.color.cat_religious,
            colorContainerRes = R.color.cat_religious_container,
        ))
        items.add(Category(
            label = "Música",
            mode = ChannelMode.ALL,
            group = "Música",
            iconRes = R.drawable.ic_music,
            colorRes = R.color.cat_music,
            colorContainerRes = R.color.cat_music_container,
        ))
        items.add(Category(
            label = "Variedades",
            mode = ChannelMode.ALL,
            group = "Variedades",
            iconRes = R.drawable.ic_variety,
            colorRes = R.color.cat_variety,
            colorContainerRes = R.color.cat_variety_container,
        ))
        items.add(Category(
            label = "24 Horas",
            mode = ChannelMode.ALL,
            group = "24 Horas",
            iconRes = R.drawable.ic_24h,
            colorRes = R.color.cat_24h,
            colorContainerRes = R.color.cat_24h_container,
        ))
        items.add(Category(
            label = "Streaming",
            mode = ChannelMode.ALL,
            group = "Streaming",
            iconRes = R.drawable.ic_streaming,
            colorRes = R.color.cat_streaming,
            colorContainerRes = R.color.cat_streaming_container,
        ))

        // --- Adultos: só aparece se o usuário habilitar nas configuracoes ---
        if (adultEnabled) {
            items.add(Category(
                label = "Adultos",
                mode = ChannelMode.ALL,
                group = "Adultos",
                iconRes = R.drawable.ic_adults,
                colorRes = R.color.cat_adults,
                colorContainerRes = R.color.cat_adults_container,
            ))
        }

        items.add(Category(
            label = "Outros",
            mode = ChannelMode.ALL,
            group = "Outros",
            iconRes = R.drawable.ic_other,
            colorRes = R.color.cat_other,
            colorContainerRes = R.color.cat_other_container,
        ))

        // --- Categorias dinâmicas vindas da playlist (que não estejam nas fixas acima) ---
        val fixedGroups = setOf(
            "Filmes", "Séries", "Infantil", "Esportes", "Notícias", "Abertos",
            "Documentários", "Animes", "Novelas", "Religiosos", "Música",
            "Variedades", "24 Horas", "Streaming", "Adultos", "Outros",
        )
        for (title in groups) {
            if (title.isNotBlank() && title !in fixedGroups) {
                // Se for grupo adulto e o recurso estiver desabilitado, pula
                if (title.equals("Adultos", ignoreCase = true) && !adultEnabled) continue
                items.add(Category(
                    label = title,
                    mode = ChannelMode.ALL,
                    group = title,
                    iconRes = R.drawable.ic_category,
                    colorRes = R.color.cat_other,
                    colorContainerRes = R.color.cat_other_container,
                ))
            }
        }

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

        val context = binding.root.context

        // Aplica cor de fundo e ícone da categoria
        val color = ContextCompat.getColor(context, item.colorRes)
        val containerColor = ContextCompat.getColor(context, item.colorContainerRes)

        binding.categoryCard.setCardBackgroundColor(containerColor)
        binding.categoryIcon.setImageResource(item.iconRes)
        binding.categoryIcon.setColorFilter(color)
        binding.categoryLabel.text = item.label

        // Estado selecionado: borda mais escura e texto mais forte
        val isSelected = position == selectedPosition
        binding.categoryCard.setStrokeWidth(if (isSelected) 2f else 0f)
        binding.categoryCard.strokeColor = ContextCompat.getColor(context, item.colorRes)

        binding.categoryLabel.setTextColor(
            if (isSelected) color else ContextCompat.getColor(context, R.color.cat_text),
        )

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

    class CategoryViewHolder(
        val binding: ItemCategoryBinding,
    ) : RecyclerView.ViewHolder(binding.root)

    companion object {
        const val ALL = "Todos"
    }
}
