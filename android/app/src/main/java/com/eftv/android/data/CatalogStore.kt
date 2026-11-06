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

    data class Metadata(
        val sourceId: String,
        val updatedAt: Long,
        val total: Int,
    )

    fun metadata(): Metadata? {
        db.rawQuery("SELECT key, value FROM meta", null).use { cursor ->
            val values = HashMap<String, String>()
            while (cursor.moveToNext()) {
                values[cursor.getString(0)] = cursor.getString(1)
            }
            val sourceId = values["source_id"] ?: return null
            val total = values["total"]?.toIntOrNull() ?: return null
            if (total <= 0) return null
            return Metadata(
                sourceId = sourceId,
                updatedAt = values["updated_at"]?.toLongOrNull() ?: 0L,
                total = total,
            )
        }
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
        val (where, args) = buildFilter(group, query, excludeAdults = excludeAdults, kind = kind)
        val select = if (isGrouped(mode, kind)) {
            "COUNT(DISTINCT $GROUP_KEY)"
        } else {
            "COUNT(*)"
        }
        db.rawQuery(
            "SELECT $select FROM ${fromClause(mode)} $where",
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
        val (where, filterArgs) = buildFilter(
            group, query, excludeAdults = excludeAdults, kind = ChannelKind.SERIES,
        )
        val args = (filterArgs + limit.toString() + offset.toString()).toTypedArray()
        // MIN(...) e o unico min/max da consulta: as colunas sem agregacao
        // (logo, url, nome...) vem da linha escolhida por ele.
        val sql = """
            SELECT c.series_key, c.series_title, c.name, c.group_title, c.logo, c.url,
                   c.user_agent, c.referer, c.tvg_id,
                   COUNT(*) AS episodes, COUNT(DISTINCT c.season) AS seasons,
                   MIN((c.logo = '') * 1000000000 + c.id) AS pick,
                   $GROUP_KEY AS gkey,
                   CASE WHEN c.series_key = '' THEN c.name_key ELSE c.series_key END AS sortkey
            FROM channels c
            $where
            GROUP BY gkey
            ORDER BY sortkey, gkey
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
     * Substitui o catalogo inteiro em uma unica transacao.
     *
     * O parser entrega um canal por vez para [feed]. Se o download falhar ou a
     * lista vier vazia, o rollback mantem o catalogo anterior intacto.
     */
    fun replace(
        sourceId: String,
        onProgress: ((Int) -> Unit)? = null,
        feed: ((Channel) -> Unit) -> Unit,
    ): Metadata {
        val updatedAt = System.currentTimeMillis()
        val groupCounts = HashMap<String, Int>()
        var total = 0

        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM channels")
            db.execSQL("DELETE FROM channel_groups")
            db.execSQL("DELETE FROM meta")

            val insertChannel = db.compileStatement(INSERT_CHANNEL)
            try {
                feed { channel ->
                    insertChannel.clearBindings()
                    insertChannel.bindString(1, channel.tvgId)
                    insertChannel.bindString(2, channel.name)
                    insertChannel.bindString(3, channel.searchKey)
                    insertChannel.bindString(4, channel.group)
                    insertChannel.bindString(5, channel.logo)
                    insertChannel.bindString(6, channel.url)
                    insertChannel.bindString(7, channel.kind.name)
                    bindNullable(insertChannel, 8, channel.userAgent)
                    bindNullable(insertChannel, 9, channel.referer)

                    // Episodios: guarda serie, temporada e episodio para agrupar.
                    val info = if (channel.kind == ChannelKind.SERIES) {
                        SeriesParser.parse(channel.name)
                    } else {
                        null
                    }
                    insertChannel.bindString(10, info?.key.orEmpty())
                    insertChannel.bindString(11, info?.title.orEmpty())
                    insertChannel.bindLong(12, (info?.season ?: 0).toLong())
                    insertChannel.bindLong(13, (info?.episode ?: 0).toLong())

                    if (insertChannel.executeInsert() != -1L) {
                        total++
                        groupCounts[channel.group] = (groupCounts[channel.group] ?: 0) + 1
                        if (total % PROGRESS_STEP == 0) onProgress?.invoke(total)
                    }
                }
            } finally {
                insertChannel.close()
            }

            if (total == 0) {
                throw IOException("A playlist nao retornou nenhum canal.")
            }

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

            val insertMeta = db.compileStatement("INSERT INTO meta(key, value) VALUES(?, ?)")
            try {
                putMeta(insertMeta, "source_id", sourceId)
                putMeta(insertMeta, "updated_at", updatedAt.toString())
                putMeta(insertMeta, "total", total.toString())
            } finally {
                insertMeta.close()
            }

            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }

        // Libera o WAL gerado pela importacao assim que possivel.
        runCatching {
            db.rawQuery("PRAGMA wal_checkpoint(TRUNCATE)", null).use { it.moveToFirst() }
        }

        return Metadata(sourceId = sourceId, updatedAt = updatedAt, total = total)
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
            clauses.add("c.group_title = ?")
            args.add(group)
        }

        if (excludeAdults) {
            clauses.add(
                "(LOWER(c.group_title) NOT LIKE '%adulto%' AND LOWER(c.group_title) NOT LIKE '%xxx%')"
            )
        }

        val query = rawQuery.normalizedForSearch()
        if (query.isNotEmpty()) {
            clauses.add("c.name_key LIKE ? ESCAPE '\\'")
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
            // Nos dois casos o catalogo e baixado de novo, preservando
            // favoritos, historico e progresso.
            if (oldVersion < 4) {
                db.execSQL("DROP TABLE IF EXISTS channels")
                db.execSQL("DROP TABLE IF EXISTS channel_groups")
                db.execSQL("DROP TABLE IF EXISTS meta")
                createSchema(db)
            }
        }

        override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            db.execSQL("DROP TABLE IF EXISTS channels")
            db.execSQL("DROP TABLE IF EXISTS channel_groups")
            db.execSQL("DROP TABLE IF EXISTS meta")
            db.execSQL("DROP TABLE IF EXISTS favorites")
            db.execSQL("DROP TABLE IF EXISTS recent")
            db.execSQL("DROP TABLE IF EXISTS progress")
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
            private const val DB_VERSION = 4
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
                (tvg_id, name, name_key, group_title, logo, url, kind, user_agent, referer,
                 series_key, series_title, season, episode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        /** Uma linha por serie; item sem marcador de episodio fica solto (chave propria). */
        private const val GROUP_KEY =
            "CASE WHEN c.series_key = '' THEN 'u' || c.id ELSE c.series_key END"
        private const val PROGRESS_STEP = 5_000
        private const val MAX_RECENTS = 100
    }
}
