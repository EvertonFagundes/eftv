package com.eftv.android.data

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.database.sqlite.SQLiteStatement
import java.io.IOException

/** Modo de navegacao da lista principal. */
enum class ChannelMode { ALL, FAVORITES, RECENTS }

/**
 * Catalogo persistido em SQLite.
 *
 * A playlist inteira nunca fica na memoria: a importacao grava canal por canal
 * e a interface pede apenas a pagina visivel. Assim o app suporta centenas de
 * milhares de canais sem crescer o heap.
 */
class CatalogStore private constructor(context: Context) {

    private val helper = CatalogDatabase(context.applicationContext)
    private val db: SQLiteDatabase by lazy { helper.writableDatabase }

    /** Indice materializado da aba Series (ver createSeriesCards). */
    @Volatile
    private var seriesIndexReady = false

    @Volatile
    private var importRecovered = false

    data class Metadata(
        val sourceId: String,
        val updatedAt: Long,
        val total: Int,
    )

    fun metadata(allowImporting: Boolean = false): Metadata? {
        val values = readMeta()
        // Importacao interrompida (app fechado no meio) nao vale como cache
        // ate [recoverInterruptedImport] validar os lotes ja gravados.
        if (!allowImporting && values["importing"] == "1") return null
        val sourceId = values["source_id"] ?: return null
        val total = values["total"]?.toIntOrNull() ?: return null
        if (total <= 0) return null
        return Metadata(
            sourceId = sourceId,
            updatedAt = values["updated_at"]?.toLongOrNull() ?: 0L,
            total = total,
        )
    }

    private fun readMeta(): Map<String, String> {
        val values = HashMap<String, String>()
        db.rawQuery("SELECT key, value FROM meta", null).use { cursor ->
            while (cursor.moveToNext()) {
                values[cursor.getString(0)] = cursor.getString(1)
            }
        }
        return values
    }

    /**
     * Recupera uma importacao que foi interrompida (app fechado no meio).
     *
     * Antes o flag `importing=1` invalidade todo o catalogo e o proximo start
     * baixava tudo de novo — mesmo com milhares de itens ja salvos. Aqui os
     * lotes commitados passam a valer como cache e so uma atualizacao manual
     * traz o restante.
     */
    fun recoverInterruptedImport() {
        if (importRecovered) return
        importRecovered = true
        val values = readMeta()
        if (values["importing"] != "1") return

        val total = countRows("channels")
        if (total <= 0) {
            // Nada foi commitado: limpa o meta para uma importacao nova.
            db.beginTransaction()
            try {
                db.execSQL("DELETE FROM meta")
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
            return
        }
        writePartialMeta(
            sourceId = values["source_id"].orEmpty(),
            updatedAt = values["updated_at"]?.toLongOrNull() ?: 0L,
            total = total,
            importing = false,
        )
        runCatching { refreshSeriesIndex() }
            .onFailure { seriesIndexReady = false }
    }

    /** Grupos que possuem canais do tipo informado (ao vivo, filme ou serie). */
    fun groups(kind: ChannelKind): List<String> {
        val result = ArrayList<String>()
        db.rawQuery(
            """
            SELECT group_title, COUNT(*) AS total
            FROM channels
            WHERE kind = ?
            GROUP BY group_title
            HAVING total > 0
            ORDER BY group_title COLLATE NOCASE
            """.trimIndent(),
            arrayOf(kind.name),
        ).use { cursor ->
            while (cursor.moveToNext()) result.add(cursor.getString(0))
        }
        return result
    }

    /** Todos os grupos do catalogo, de qualquer tipo. */
    fun allGroups(): List<String> {
        val result = ArrayList<String>()
        db.rawQuery(
            "SELECT DISTINCT group_title FROM channels ORDER BY group_title COLLATE NOCASE",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) result.add(cursor.getString(0))
        }
        return result
    }

    data class GroupCount(val title: String, val count: Int)

    /**
     * Grupos do tipo informado com a quantidade de itens de cada um.
     *
     * A tela de categorias mostra a quantidade para o cliente saber o que vale
     * a pena abrir e para nao exibir grupo vazio (a lista fixa antiga oferecia
     * categorias que a playlist nem tinha).
     */
    fun groupsWithCounts(kind: ChannelKind): List<GroupCount> {
        val result = ArrayList<GroupCount>()
        db.rawQuery(
            """
            SELECT group_title, COUNT(*) AS total
            FROM channels
            WHERE kind = ?
            GROUP BY group_title
            HAVING total > 0
            ORDER BY total DESC, group_title COLLATE NOCASE
            """.trimIndent(),
            arrayOf(kind.name),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                result.add(GroupCount(cursor.getString(0), cursor.getInt(1)))
            }
        }
        return result
    }

    /**
     * Posicao do primeiro item cujo nome comeca com [letter].
     *
     * Alimenta a barra A-Z: com 2.261 canais, arrastar a lista ate "S" e
     * inviavel. Retorna -1 quando nao ha nenhum item com a letra.
     */
    fun firstIndexForLetter(
        group: String?,
        query: String,
        mode: ChannelMode,
        kind: ChannelKind?,
        excludeAdults: Boolean,
        letter: Char,
    ): Int {
        val prefix = letter.lowercaseChar().toString()
        if (isGrouped(mode, kind)) {
            if (!ensureSeriesIndex()) return -1
            val (where, args) = buildFilter(
                group, query, excludeAdults = excludeAdults, kind = ChannelKind.SERIES,
            )
            val condition = if (where.isEmpty()) {
                "WHERE c.sortkey < ?"
            } else {
                "$where AND c.sortkey < ?"
            }
            val totalBefore = db.rawQuery(
                "SELECT COUNT(*) FROM series_cards c $condition",
                (args + prefix).toTypedArray(),
            ).use { cursor ->
                if (cursor.moveToFirst()) cursor.getInt(0) else 0
            }
            val totalAll = countInternal(group, query, mode, kind, excludeAdults)
            return if (totalBefore >= totalAll) -1 else totalBefore
        }

        val (where, args) = buildFilter(group, query, excludeAdults = excludeAdults, kind = kind)
        // buildFilter ja devolve a clausula com "WHERE" (ou vazio).
        val condition = if (where.isEmpty()) {
            "WHERE c.name_key < ?"
        } else {
            "$where AND c.name_key < ?"
        }
        val sql = "SELECT COUNT(*) FROM ${fromClause(mode)} $condition"

        val totalBefore = db.rawQuery(sql, (args + prefix).toTypedArray()).use { cursor ->
            if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
        val totalAll = countInternal(group, query, mode, kind, excludeAdults)
        return if (totalBefore >= totalAll) -1 else totalBefore
    }

    /** O catalogo tem algum grupo de conteudo adulto? */
    fun hasAdultGroup(): Boolean =
        allGroups().any { ChannelKind.isAdultGroup(it) }

    fun count(
        group: String?,
        query: String,
        mode: ChannelMode = ChannelMode.ALL,
        kind: ChannelKind? = null,
    ): Int = countInternal(group, query, mode, kind, excludeAdults = false)

    /** Conta canais excluindo o grupo Adultos (usado quando conteudo adulto esta desabilitado). */
    fun countExcludingAdults(
        group: String?,
        query: String,
        mode: ChannelMode = ChannelMode.ALL,
        kind: ChannelKind? = null,
    ): Int = countInternal(group, query, mode, kind, excludeAdults = true)

    fun page(
        group: String?,
        query: String,
        limit: Int,
        offset: Int,
        mode: ChannelMode = ChannelMode.ALL,
        kind: ChannelKind? = null,
    ): List<Channel> = pageInternal(group, query, limit, offset, mode, kind, excludeAdults = false)

    /** Pagina canais excluindo o grupo Adultos (usado quando conteudo adulto esta desabilitado). */
    fun pageExcludingAdults(
        group: String?,
        query: String,
        limit: Int,
        offset: Int,
        mode: ChannelMode = ChannelMode.ALL,
        kind: ChannelKind? = null,
    ): List<Channel> = pageInternal(group, query, limit, offset, mode, kind, excludeAdults = true)

    /** Na aba Series (sem favoritos/historico) cada serie vira um unico card. */
    private fun isGrouped(mode: ChannelMode, kind: ChannelKind?): Boolean =
        kind == ChannelKind.SERIES && mode == ChannelMode.ALL

    private fun countInternal(
        group: String?,
        query: String,
        mode: ChannelMode,
        kind: ChannelKind?,
        excludeAdults: Boolean,
    ): Int {
        if (isGrouped(mode, kind)) {
            // Uma linha por serie no indice materializado: contar e paginar
            // nao varre mais os ~240 mil episodios.
            if (!ensureSeriesIndex()) return 0
            val (where, args) = buildFilter(
                group, query, excludeAdults = excludeAdults, kind = ChannelKind.SERIES,
            )
            db.rawQuery(
                "SELECT COUNT(*) FROM series_cards c $where",
                args.toTypedArray(),
            ).use { cursor ->
                return if (cursor.moveToFirst()) cursor.getInt(0) else 0
            }
        }

        val (where, args) = buildFilter(group, query, excludeAdults = excludeAdults, kind = kind)
        db.rawQuery(
            "SELECT COUNT(*) FROM ${fromClause(mode)} $where",
            args.toTypedArray(),
        ).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
    }

    private fun pageInternal(
        group: String?,
        query: String,
        limit: Int,
        offset: Int,
        mode: ChannelMode,
        kind: ChannelKind?,
        excludeAdults: Boolean,
    ): List<Channel> {
        if (isGrouped(mode, kind)) {
            return seriesPage(group, query, limit, offset, excludeAdults)
        }

        val (where, filterArgs) = buildFilter(group, query, excludeAdults = excludeAdults, kind = kind)
        val args = (filterArgs + limit.toString() + offset.toString()).toTypedArray()
        val sql = """
            SELECT c.tvg_id, c.name, c.group_title, c.logo, c.url, c.user_agent, c.referer,
                   c.kind, COALESCE(p.position_ms, 0), COALESCE(p.duration_ms, 0),
                   c.series_key, c.series_title, c.season, c.episode
            FROM ${fromClause(mode)}
            LEFT JOIN progress p ON p.url = c.url
            $where
            ORDER BY ${orderClause(mode)}
            LIMIT ? OFFSET ?
        """.trimIndent()

        val result = ArrayList<Channel>(limit)
        db.rawQuery(sql, args).use { cursor ->
            while (cursor.moveToNext()) result.add(readEpisodeRow(cursor))
        }
        return result
    }

    /**
     * Lista agrupada da aba Series: uma linha por serie, com a capa do primeiro
     * episodio que tem imagem. Itens sem marcador de episodio ficam soltos.
     */
    private fun seriesPage(
        group: String?,
        query: String,
        limit: Int,
        offset: Int,
        excludeAdults: Boolean,
    ): List<Channel> {
        if (!ensureSeriesIndex()) return emptyList()
        val (where, filterArgs) = buildFilter(
            group, query, excludeAdults = excludeAdults, kind = ChannelKind.SERIES,
        )
        val args = (filterArgs + limit.toString() + offset.toString()).toTypedArray()
        val sql = """
            SELECT c.series_key, c.series_title, c.name, c.group_title, c.logo, c.url,
                   c.user_agent, c.referer, c.tvg_id, c.episodes, c.seasons
            FROM series_cards c
            $where
            ORDER BY c.sortkey, c.gkey
            LIMIT ? OFFSET ?
        """.trimIndent()

        val result = ArrayList<Channel>(limit)
        db.rawQuery(sql, args).use { cursor ->
            while (cursor.moveToNext()) {
                val key = cursor.getString(0)
                val title = cursor.getString(1)
                result.add(
                    Channel(
                        name = if (key.isEmpty()) cursor.getString(2) else title,
                        group = cursor.getString(3),
                        logo = cursor.getString(4),
                        url = cursor.getString(5),
                        userAgent = if (cursor.isNull(6)) null else cursor.getString(6),
                        referer = if (cursor.isNull(7)) null else cursor.getString(7),
                        tvgId = cursor.getString(8),
                        kind = ChannelKind.SERIES,
                        seriesKey = key,
                        seriesTitle = title,
                        seriesEpisodes = if (key.isEmpty()) 0 else cursor.getInt(9),
                        seriesSeasons = if (key.isEmpty()) 0 else cursor.getInt(10),
                    )
                )
            }
        }
        return result
    }

    /**
     * Garante o indice materializado da aba Series.
     *
     * Bancos antigos (ou uma importacao interrompida) nao tem a tabela
     * preenchida. Monta uma vez, fora da importacao; durante ela a aba
     * mostra o indice anterior (ou vazio, na primeira instalacao).
     */
    private fun ensureSeriesIndex(): Boolean {
        if (seriesIndexReady) return true
        synchronized(this) {
            if (seriesIndexReady) return true
            if (isImporting()) {
                // Importacao em andamento: usa o indice anterior, se houver,
                // mas nao remonta no meio dos lotes.
                return countRows("series_cards") > 0
            }

            if (countRows("series_cards") == 0) {
                if (countRows("channels", "kind = 'SERIES'") == 0) {
                    seriesIndexReady = true
                    return true
                }
                val rebuilt = runCatching { rebuildSeriesIndex() }.isSuccess
                if (!rebuilt) return false
            }
            seriesIndexReady = true
            return true
        }
    }

    private fun refreshSeriesIndex() {
        synchronized(this) {
            rebuildSeriesIndex()
            seriesIndexReady = true
        }
    }

    private fun isImporting(): Boolean =
        db.rawQuery("SELECT value FROM meta WHERE key = 'importing'", null).use { cursor ->
            cursor.moveToFirst() && cursor.getString(0) == "1"
        }

    private fun countRows(table: String, condition: String? = null): Int {
        val where = condition?.let { " WHERE $it" }.orEmpty()
        db.rawQuery("SELECT COUNT(*) FROM $table$where", null).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
    }

    private fun rebuildSeriesIndex() {
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM series_cards")
            db.execSQL(BUILD_SERIES_CARDS)
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    /** Todos os episodios de uma serie, em ordem de temporada e episodio. */
    fun episodes(seriesKey: String): List<Channel> {
        if (seriesKey.isEmpty()) return emptyList()
        val sql = """
            SELECT c.tvg_id, c.name, c.group_title, c.logo, c.url, c.user_agent, c.referer,
                   c.kind, COALESCE(p.position_ms, 0), COALESCE(p.duration_ms, 0),
                   c.series_key, c.series_title, c.season, c.episode
            FROM channels c
            LEFT JOIN progress p ON p.url = c.url
            WHERE c.kind = 'SERIES' AND c.series_key = ?
            ORDER BY c.season, c.episode, c.id
        """.trimIndent()

        val result = ArrayList<Channel>()
        db.rawQuery(sql, arrayOf(seriesKey)).use { cursor ->
            while (cursor.moveToNext()) result.add(readEpisodeRow(cursor))
        }
        return result
    }

    private fun readEpisodeRow(cursor: Cursor): Channel = Channel(
        name = cursor.getString(1),
        group = cursor.getString(2),
        logo = cursor.getString(3),
        url = cursor.getString(4),
        tvgId = cursor.getString(0),
        userAgent = if (cursor.isNull(5)) null else cursor.getString(5),
        referer = if (cursor.isNull(6)) null else cursor.getString(6),
        kind = kindFromDb(cursor.getString(7)),
        progressMs = cursor.getLong(8),
        durationMs = cursor.getLong(9),
        seriesKey = cursor.getString(10),
        seriesTitle = cursor.getString(11),
        season = cursor.getInt(12),
        episode = cursor.getInt(13),
    )

    // ------------------------------------------------------------------
    // Favoritos e historico (navegacao rapida)
    // ------------------------------------------------------------------

    fun favoriteUrls(): Set<String> {
        val result = HashSet<String>()
        db.rawQuery("SELECT url FROM favorites", null).use { cursor ->
            while (cursor.moveToNext()) result.add(cursor.getString(0))
        }
        return result
    }

    fun isFavorite(url: String): Boolean {
        db.rawQuery("SELECT 1 FROM favorites WHERE url = ? LIMIT 1", arrayOf(url)).use {
            return it.moveToFirst()
        }
    }

    /** Adiciona/remove um favorito e devolve o estado final. */
    fun setFavorite(url: String, favorite: Boolean): Boolean {
        if (favorite) {
            db.execSQL(
                "INSERT OR REPLACE INTO favorites(url, added_at) VALUES(?, ?)",
                arrayOf(url, System.currentTimeMillis()),
            )
        } else {
            db.execSQL("DELETE FROM favorites WHERE url = ?", arrayOf(url))
        }
        return favorite
    }

    /** Marca o canal como aberto agora e mantem o historico curto. */
    fun markRecent(url: String) {
        db.execSQL(
            "INSERT OR REPLACE INTO recent(url, opened_at) VALUES(?, ?)",
            arrayOf(url, System.currentTimeMillis()),
        )
        db.execSQL(
            """
            DELETE FROM recent WHERE url NOT IN (
                SELECT url FROM recent ORDER BY opened_at DESC LIMIT $MAX_RECENTS
            )
            """.trimIndent()
        )
    }

    /** Salva a posicao de um conteudo sob demanda. */
    fun saveProgress(url: String, positionMs: Long, durationMs: Long) {
        if (url.isBlank() || durationMs <= 0) return
        db.execSQL(
            "INSERT OR REPLACE INTO progress(url, position_ms, duration_ms, updated_at) VALUES(?, ?, ?, ?)",
            arrayOf(url, positionMs.coerceAtLeast(0), durationMs, System.currentTimeMillis()),
        )
    }

    /** Remove o progresso (conteudo concluido ou removido da lista). */
    fun clearProgress(url: String) {
        db.execSQL("DELETE FROM progress WHERE url = ?", arrayOf(url))
    }

    /** Progresso salvo de um item, se existir. */
    fun progress(url: String): WatchProgress? {
        db.rawQuery(
            "SELECT position_ms, duration_ms FROM progress WHERE url = ? LIMIT 1",
            arrayOf(url),
        ).use { cursor ->
            return if (cursor.moveToFirst()) {
                WatchProgress(cursor.getLong(0), cursor.getLong(1))
            } else {
                null
            }
        }
    }

    /** Progresso de varios itens de uma vez (usado pelas capas do catalogo). */
    fun progressFor(urls: Collection<String>): Map<String, WatchProgress> {
        if (urls.isEmpty()) return emptyMap()
        val result = HashMap<String, WatchProgress>()
        urls.distinct().chunked(400).forEach { chunk ->
            val placeholders = chunk.joinToString(",") { "?" }
            db.rawQuery(
                "SELECT url, position_ms, duration_ms FROM progress WHERE url IN ($placeholders)",
                chunk.toTypedArray(),
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    result[cursor.getString(0)] =
                        WatchProgress(cursor.getLong(1), cursor.getLong(2))
                }
            }
        }
        return result
    }

    /**
     * Conteudo sob demanda parado, mais recente primeiro: base do carrossel
     * "Continuar assistindo" da home.
     *
     * Deixa de fora o que ja foi concluido (ou quase) e o que tem menos de
     * 1 minuto assistido, para nao oferecer aberturas acidentais. As colunas
     * seguem a ordem de [readEpisodeRow].
     */
    fun continueWatching(limit: Int = 12): List<Channel> {
        val sql = """
            SELECT c.tvg_id, c.name, c.group_title, c.logo, c.url, c.user_agent, c.referer,
                   c.kind, p.position_ms, p.duration_ms,
                   c.series_key, c.series_title, c.season, c.episode
            FROM progress p
            JOIN channels c ON c.url = p.url
            WHERE c.kind <> 'LIVE'
              AND p.duration_ms > 0
              AND p.position_ms >= 60000
              AND p.position_ms <= p.duration_ms - 30000
            ORDER BY p.updated_at DESC
            LIMIT ?
        """.trimIndent()

        val result = ArrayList<Channel>(limit)
        db.rawQuery(sql, arrayOf(limit.toString())).use { cursor ->
            while (cursor.moveToNext()) result.add(readEpisodeRow(cursor))
        }
        return result
    }

    /**
     * Substitui o catalogo em lotes.
     *
     * O parser entrega um canal por vez para [feed]. A cada [batchSize]
     * canais a transacao e commitada e o metadado parcial e atualizado, para
     * o app exibir o que ja chegou enquanto o restante e importado. Se o
     * download falhar no meio, o lote em andamento e revertido e os lotes
     * anteriores permanecem com metadado parcial consistente.
     */
    fun replace(
        sourceId: String,
        onProgress: ((Int) -> Unit)? = null,
        feed: ((Channel) -> Unit) -> Unit,
    ): Metadata {
        val updatedAt = System.currentTimeMillis()
        val groupCounts = HashMap<String, Int>()
        var total = 0

        // Limpa em transacao propria para a UI nao ver estado inconsistente
        // enquanto a importacao roda.
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM channels")
            db.execSQL("DELETE FROM channel_groups")
            db.execSQL("DELETE FROM series_cards")
            db.execSQL("DELETE FROM meta")
            // Enquanto a importacao roda, o catalogo nao conta como cache
            // valido. O indice da aba Series e mantido lote a lote abaixo, por
            // isso nao precisa ser remontado no meio da importacao.
            db.execSQL("INSERT INTO meta(key, value) VALUES('importing', '1')")
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
            seriesIndexReady = true
        }

        // Insere em lotes commitados, para que o que ja foi importado fique
        // visivel e assistivel enquanto o restante continua em segundo plano.
        // 2.000 reduz para 1/4 o numero de commits/WAL sem atrasar a primeira
        // pagina do catalogo de forma perceptivel.
        val batchSize = 2_000
        var batchCount = 0
        var committedTotal = 0
        var insertChannel = db.compileStatement(INSERT_CHANNEL)
        var insertSeriesCard = db.compileStatement(INSERT_SERIES_CARD)
        var updateSeriesCard = db.compileStatement(UPDATE_SERIES_CARD)
        var failure: Throwable? = null
        db.beginTransaction()
        try {
            feed { channel ->
                insertChannel.clearBindings()
                insertChannel.bindString(1, channel.tvgId)
                insertChannel.bindString(2, channel.name)
                insertChannel.bindString(3, channel.searchKey)
                insertChannel.bindString(4, channel.group)
                insertChannel.bindString(5, channel.group.normalizedForSearch())
                insertChannel.bindString(6, channel.logo)
                insertChannel.bindString(7, channel.url)
                insertChannel.bindString(8, channel.kind.name)
                bindNullable(insertChannel, 9, channel.userAgent)
                bindNullable(insertChannel, 10, channel.referer)

                // Episodios: guarda serie, temporada e episodio para agrupar.
                val info = if (channel.kind == ChannelKind.SERIES) {
                    SeriesParser.parse(channel.name)
                } else {
                    null
                }
                insertChannel.bindString(11, info?.key.orEmpty())
                insertChannel.bindString(12, info?.title.orEmpty())
                insertChannel.bindLong(13, (info?.season ?: 0).toLong())
                insertChannel.bindLong(14, (info?.episode ?: 0).toLong())

                val rowId = insertChannel.executeInsert()
                if (rowId != -1L) {
                    total++
                    groupCounts[channel.group] = (groupCounts[channel.group] ?: 0) + 1

                    // Mantem o indice das series crescente junto com o lote.
                    // Sem isso a aba Series so aparecia no fim da importacao.
                    if (info != null) {
                        val grouped = info.key.isNotEmpty()
                        val gkey = if (grouped) info.key else "u$rowId"
                        val sortkey = if (grouped) info.key else channel.searchKey
                        insertSeriesCard.clearBindings()
                        insertSeriesCard.bindString(1, gkey)
                        insertSeriesCard.bindString(2, if (grouped) info.key else "")
                        insertSeriesCard.bindString(3, sortkey)
                        insertSeriesCard.bindString(4, info.title)
                        insertSeriesCard.bindString(5, channel.name)
                        insertSeriesCard.bindString(6, channel.searchKey)
                        insertSeriesCard.bindString(7, channel.group)
                        insertSeriesCard.bindString(8, channel.group.normalizedForSearch())
                        insertSeriesCard.bindString(9, channel.logo)
                        insertSeriesCard.bindString(10, channel.url)
                        bindNullable(insertSeriesCard, 11, channel.userAgent)
                        bindNullable(insertSeriesCard, 12, channel.referer)
                        insertSeriesCard.bindString(13, channel.tvgId)
                        insertSeriesCard.bindLong(14, info.season.toLong())
                        insertSeriesCard.executeInsert()

                        updateSeriesCard.clearBindings()
                        updateSeriesCard.bindLong(1, info.season.toLong())
                        updateSeriesCard.bindString(2, channel.logo)
                        updateSeriesCard.bindString(3, channel.logo)
                        updateSeriesCard.bindString(4, gkey)
                        updateSeriesCard.executeUpdateDelete()
                    }

                    batchCount++
                    if (batchCount >= batchSize) {
                        // Commita o lote e reabre a transacao para o proximo.
                        closeImportStatements(insertChannel, insertSeriesCard, updateSeriesCard)
                        db.setTransactionSuccessful()
                        db.endTransaction()
                        committedTotal = total
                        // Atualiza meta parcial para a UI enxergar o progresso.
                        writePartialMeta(sourceId, updatedAt, committedTotal)
                        // Avisa a cada lote commitado: o que chegou ja pode ser usado.
                        onProgress?.invoke(committedTotal)
                        db.beginTransaction()
                        insertChannel = db.compileStatement(INSERT_CHANNEL)
                        insertSeriesCard = db.compileStatement(INSERT_SERIES_CARD)
                        updateSeriesCard = db.compileStatement(UPDATE_SERIES_CARD)
                        batchCount = 0
                    }
                }
            }

            if (total == 0) {
                throw IOException("A playlist nao retornou nenhum canal.")
            }
            if (batchCount > 0) onProgress?.invoke(total)
            // Commita o lote final (pode ter menos de batchSize canais).
            db.setTransactionSuccessful()
        } catch (t: Throwable) {
            failure = t
        } finally {
            closeImportStatements(insertChannel, insertSeriesCard, updateSeriesCard)
            // Fecha a transacao corrente: commit se deu certo, rollback se nao.
            if (db.inTransaction()) db.endTransaction()
        }

        val error = failure
        if (error != null) {
            // O lote incompleto foi revertido; mantem os lotes ja commitados
            // com metadado consistente para o app nao exibir um catalogo vazio.
            if (committedTotal > 0) {
                // Importacao encerrada (mesmo com erro): o catalogo parcial
                // e valido como cache e a aba Series precisa do indice novo.
                runCatching {
                    writePartialMeta(sourceId, updatedAt, committedTotal, importing = false)
                }
                runCatching { refreshSeriesIndex() }
                    .onFailure { seriesIndexReady = false }
            }
            throw error
        }

        // Grupos + meta final em transacao propria.
        val finishedAt = System.currentTimeMillis()
        db.beginTransaction()
        try {
            val insertGroup = db.compileStatement(
                "INSERT INTO channel_groups(title, total) VALUES(?, ?)"
            )
            try {
                for ((title, count) in groupCounts) {
                    insertGroup.clearBindings()
                    insertGroup.bindString(1, title)
                    insertGroup.bindLong(2, count.toLong())
                    insertGroup.executeInsert()
                }
            } finally {
                insertGroup.close()
            }

            db.execSQL("DELETE FROM meta")
            val insertMeta = db.compileStatement("INSERT INTO meta(key, value) VALUES(?, ?)")
            try {
                putMeta(insertMeta, "source_id", sourceId)
                putMeta(insertMeta, "updated_at", finishedAt.toString())
                putMeta(insertMeta, "total", total.toString())
                putMeta(insertMeta, "importing", "0")
            } finally {
                insertMeta.close()
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }

        // Monta o indice da aba Series uma vez por importacao.
        runCatching { refreshSeriesIndex() }
            .onFailure { seriesIndexReady = false }

        // Libera o WAL gerado pela importacao assim que possivel.
        runCatching {
            db.rawQuery("PRAGMA wal_checkpoint(TRUNCATE)", null).use { it.moveToFirst() }
        }

        return Metadata(sourceId = sourceId, updatedAt = finishedAt, total = total)
    }

    private fun closeImportStatements(vararg statements: SQLiteStatement) {
        statements.forEach { runCatching { it.close() } }
    }

    private fun writePartialMeta(
        sourceId: String,
        updatedAt: Long,
        total: Int,
        importing: Boolean = true,
    ) {
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM meta")
            val insertMeta = db.compileStatement("INSERT INTO meta(key, value) VALUES(?, ?)")
            try {
                putMeta(insertMeta, "source_id", sourceId)
                putMeta(insertMeta, "updated_at", updatedAt.toString())
                putMeta(insertMeta, "total", total.toString())
                putMeta(insertMeta, "importing", if (importing) "1" else "0")
            } finally {
                insertMeta.close()
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    private fun buildFilter(
        group: String?,
        rawQuery: String,
        excludeAdults: Boolean = false,
        kind: ChannelKind? = null,
    ): Pair<String, List<String>> {
        val clauses = ArrayList<String>(4)
        val args = ArrayList<String>(4)

        if (kind != null) {
            clauses.add("c.kind = ?")
            args.add(kind.name)
        }

        if (!group.isNullOrBlank()) {
            if (group == FreeTv.GROUP) {
                // Categoria virtual montada pelo nome do canal (TV aberta).
                val (sql, extraArgs) = FreeTv.clause()
                clauses.add(sql)
                args.addAll(extraArgs)
            } else {
                clauses.add("c.group_title = ?")
                args.add(group)
            }
        }

        if (excludeAdults) {
            // Mesma lista de palavras usada na categoria (ChannelKind.isAdultGroup),
            // para o canal nao aparecer na lista mas sumir da categoria (e vice-versa).
            // group_key ja vem minusculo e sem acento, igual a normalizacao do Kotlin.
            val conditions = ChannelKind.ADULT_GROUP_KEYWORDS.joinToString(" AND ") {
                "c.group_key NOT LIKE ?"
            }
            clauses.add("($conditions)")
            ChannelKind.ADULT_GROUP_KEYWORDS.forEach { args.add("%$it%") }
        }

        val query = rawQuery.normalizedForSearch()
        if (query.isNotEmpty()) {
            // Busca no nome do canal e tambem no grupo ("esportes" traz o grupo
            // Esportes inteiro). Ambas as colunas sao sem acento e minusculas.
            clauses.add("(c.name_key LIKE ? ESCAPE '\\' OR c.group_key LIKE ? ESCAPE '\\')")
            args.add("%${escapeLike(query)}%")
            args.add("%${escapeLike(query)}%")
        }

        val where = if (clauses.isEmpty()) "" else "WHERE ${clauses.joinToString(" AND ")}"
        return where to args
    }

    private fun fromClause(mode: ChannelMode): String = when (mode) {
        ChannelMode.ALL -> "channels c"
        ChannelMode.FAVORITES -> "channels c INNER JOIN favorites f ON f.url = c.url"
        ChannelMode.RECENTS -> "channels c INNER JOIN recent r ON r.url = c.url"
    }

    private fun orderClause(mode: ChannelMode): String = when (mode) {
        ChannelMode.ALL -> "c.name_key ASC, c.id ASC"
        ChannelMode.FAVORITES -> "f.added_at DESC, c.name_key ASC, c.id ASC"
        ChannelMode.RECENTS -> "r.opened_at DESC, c.name_key ASC, c.id ASC"
    }

    private fun escapeLike(value: String): String =
        value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    private fun kindFromDb(value: String?): ChannelKind =
        runCatching { ChannelKind.valueOf(value.orEmpty()) }
            .getOrDefault(ChannelKind.LIVE)

    private fun bindNullable(statement: SQLiteStatement, index: Int, value: String?) {
        if (value.isNullOrBlank()) {
            statement.bindNull(index)
        } else {
            statement.bindString(index, value)
        }
    }

    private fun putMeta(statement: SQLiteStatement, key: String, value: String) {
        statement.clearBindings()
        statement.bindString(1, key)
        statement.bindString(2, value)
        statement.executeInsert()
    }

    private class CatalogDatabase(context: Context) :
        SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {

        init {
            setWriteAheadLoggingEnabled(true)
        }

        override fun onCreate(db: SQLiteDatabase) {
            createSchema(db)
        }

        override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            // v3: tipo do conteudo (ao vivo / filme / serie).
            // v4: serie, temporada e episodio (agrupamento de series).
            // v5: group_key (grupo sem acento, para a busca por categoria).
            // v6: series_cards (uma linha por serie, para a aba Series ser
            //     paginada sem reagrupar o catalogo inteiro a cada pagina).
            // Nos casos que trocam o catalogo, ele e baixado de novo,
            // preservando favoritos, historico e progresso.
            if (oldVersion < 4) {
                db.execSQL("DROP TABLE IF EXISTS channels")
                db.execSQL("DROP TABLE IF EXISTS channel_groups")
                db.execSQL("DROP TABLE IF EXISTS meta")
                createSchema(db)
            } else if (oldVersion < 5) {
                // So a coluna nova: o catalogo existente continua valido.
                db.execSQL(
                    "ALTER TABLE channels ADD COLUMN group_key TEXT NOT NULL DEFAULT ''",
                )
                backfillGroupKey(db)
            }
            if (oldVersion in 4..5) {
                // O indice e montado sob demanda na primeira abertura da aba.
                createSeriesCards(db)
            }
        }

        /**
         * Preenche group_key a partir de group_title. Ha poucos grupos
         * distintos entao atualizamos uma vez por grupo, nao por canal.
         */
        private fun backfillGroupKey(db: SQLiteDatabase) {
            val groups = LinkedHashSet<String>()
            db.rawQuery("SELECT DISTINCT group_title FROM channels", null).use { cursor ->
                while (cursor.moveToNext()) groups.add(cursor.getString(0))
            }
            val update = db.compileStatement(
                "UPDATE channels SET group_key = ? WHERE group_title = ?",
            )
            try {
                for (title in groups) {
                    update.clearBindings()
                    update.bindString(1, title.normalizedForSearch())
                    update.bindString(2, title)
                    update.executeUpdateDelete()
                }
            } finally {
                update.close()
            }
        }

        override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            // Preserva dados pessoais (favoritos, historico, progresso) no downgrade.
            db.execSQL("DROP TABLE IF EXISTS channels")
            db.execSQL("DROP TABLE IF EXISTS channel_groups")
            db.execSQL("DROP TABLE IF EXISTS series_cards")
            db.execSQL("DROP TABLE IF EXISTS meta")
            createSchema(db)
        }

        private fun createSchema(db: SQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE channels (
                    id INTEGER PRIMARY KEY,
                    tvg_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    group_title TEXT NOT NULL,
                    group_key TEXT NOT NULL DEFAULT '',
                    logo TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'LIVE',
                    user_agent TEXT,
                    referer TEXT,
                    series_key TEXT NOT NULL DEFAULT '',
                    series_title TEXT NOT NULL DEFAULT '',
                    season INTEGER NOT NULL DEFAULT 0,
                    episode INTEGER NOT NULL DEFAULT 0
                )
                """.trimIndent()
            )
            db.execSQL("CREATE UNIQUE INDEX idx_channels_url ON channels(url)")
            db.execSQL(
                "CREATE INDEX idx_channels_kind_name ON channels(kind, name_key, id)"
            )
            db.execSQL(
                "CREATE INDEX idx_channels_kind_group_name ON channels(kind, group_title, name_key, id)"
            )
            db.execSQL(
                "CREATE INDEX idx_channels_series ON channels(kind, series_key, season, episode)"
            )
            db.execSQL(
                "CREATE TABLE channel_groups (title TEXT PRIMARY KEY, total INTEGER NOT NULL)"
            )
            db.execSQL("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            createPersonalTables(db)
            createSeriesCards(db)
        }

        /**
         * Uma linha por serie, montada no fim da importacao.
         *
         * Sem ela, cada pagina da aba Series reagrupava ~240 mil episodios
         * com window functions: a tela ficava minutos em "Carregando..." e
         * consumia centenas de MB.
         */
        private fun createSeriesCards(db: SQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS series_cards (
                    gkey TEXT PRIMARY KEY,
                    series_key TEXT NOT NULL DEFAULT '',
                    sortkey TEXT NOT NULL,
                    series_title TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL,
                    group_title TEXT NOT NULL,
                    group_key TEXT NOT NULL,
                    logo TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    user_agent TEXT,
                    referer TEXT,
                    tvg_id TEXT NOT NULL DEFAULT '',
                    episodes INTEGER NOT NULL DEFAULT 0,
                    seasons INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL DEFAULT 'SERIES'
                )
                """.trimIndent()
            )
            db.execSQL(
                "CREATE INDEX IF NOT EXISTS idx_series_cards_sort " +
                    "ON series_cards(sortkey, gkey)"
            )
            db.execSQL(
                "CREATE INDEX IF NOT EXISTS idx_series_cards_filters " +
                    "ON series_cards(group_key, name_key)"
            )
        }

        private fun createPersonalTables(db: SQLiteDatabase) {
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    url TEXT PRIMARY KEY,
                    added_at INTEGER NOT NULL
                )
                """.trimIndent()
            )
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS recent (
                    url TEXT PRIMARY KEY,
                    opened_at INTEGER NOT NULL
                )
                """.trimIndent()
            )
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_recent_opened ON recent(opened_at DESC)")
            db.execSQL(
                """
                CREATE TABLE IF NOT EXISTS progress (
                    url TEXT PRIMARY KEY,
                    position_ms INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """.trimIndent()
            )
        }

        companion object {
            private const val DB_NAME = "catalog.db"
            private const val DB_VERSION = 6
        }
    }

    companion object {
        @Volatile
        private var instance: CatalogStore? = null

        /** Um unico banco por processo: sobrevive a troca de telas. */
        fun get(context: Context): CatalogStore =
            instance ?: synchronized(this) {
                instance ?: CatalogStore(context.applicationContext).also { instance = it }
            }

        private const val INSERT_CHANNEL = """
            INSERT OR IGNORE INTO channels
                (tvg_id, name, name_key, group_title, group_key, logo, url, kind,
                 user_agent, referer, series_key, series_title, season, episode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        /**
         * Card de serie gravado junto com o episodio (INSERT OR IGNORE para
         * funcionar em SQLite antigo, onde nao ha UPSERT). A primeira linha
         * define titulo/capa/URL; [UPDATE_SERIES_CARD] acrescenta episodios,
         * temporadas e uma capa quando o provedor a entrega depois.
         */
        private const val INSERT_SERIES_CARD = """
            INSERT OR IGNORE INTO series_cards
                (gkey, series_key, sortkey, series_title, name, name_key,
                 group_title, group_key, logo, url, user_agent, referer, tvg_id,
                 episodes, seasons, kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'SERIES')
        """

        private const val UPDATE_SERIES_CARD = """
            UPDATE series_cards SET
                episodes = episodes + 1,
                seasons = MAX(seasons, ?),
                logo = CASE WHEN logo = '' AND ? <> '' THEN ? ELSE logo END
            WHERE gkey = ?
        """

        /** Uma linha por serie; item sem marcador de episodio fica solto (chave propria). */
        private val BUILD_SERIES_CARDS = """
            INSERT INTO series_cards
                (gkey, series_key, sortkey, series_title, name, name_key,
                 group_title, group_key, logo, url, user_agent, referer, tvg_id,
                 episodes, seasons, kind)
            WITH filtered AS (
                SELECT c.*,
                       CASE WHEN c.series_key = '' THEN 'u' || c.id ELSE c.series_key END AS gkey,
                       CASE WHEN c.series_key = '' THEN c.name_key ELSE c.series_key END AS sortkey
                FROM channels c
                WHERE c.kind = 'SERIES'
            ),
            counts AS (
                SELECT gkey,
                       COUNT(*) AS episodes,
                       COUNT(DISTINCT season) AS seasons
                FROM filtered
                GROUP BY gkey
            ),
            ranked AS (
                SELECT f.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY f.gkey
                           ORDER BY (f.logo = '') ASC, f.season ASC, f.episode ASC, f.id ASC
                       ) AS rn
                FROM filtered f
            )
            SELECT r.gkey, r.series_key, r.sortkey, r.series_title, r.name, r.sortkey,
                   r.group_title, r.group_key, r.logo, r.url, r.user_agent, r.referer,
                   r.tvg_id, cnt.episodes, cnt.seasons, 'SERIES'
            FROM ranked r
            JOIN counts cnt ON cnt.gkey = r.gkey
            WHERE r.rn = 1
        """.trimIndent()

        private const val MAX_RECENTS = 100
    }
}
