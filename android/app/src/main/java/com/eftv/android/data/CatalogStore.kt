package com.eftv.android.data

import android.content.Context
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

    fun groups(): List<String> {
        val result = ArrayList<String>()
        db.rawQuery(
            "SELECT title FROM channel_groups WHERE total > 0 ORDER BY title COLLATE NOCASE",
            null,
        ).use { cursor ->
            while (cursor.moveToNext()) result.add(cursor.getString(0))
        }
        return result
    }

    fun count(group: String?, query: String, mode: ChannelMode = ChannelMode.ALL): Int {
        val (where, args) = buildFilter(group, query)
        db.rawQuery(
            "SELECT COUNT(*) FROM ${fromClause(mode)} $where",
            args.toTypedArray(),
        ).use { cursor ->
            return if (cursor.moveToFirst()) cursor.getInt(0) else 0
        }
    }

    fun page(
        group: String?,
        query: String,
        limit: Int,
        offset: Int,
        mode: ChannelMode = ChannelMode.ALL,
    ): List<Channel> {
        val (where, filterArgs) = buildFilter(group, query)
        val args = (filterArgs + limit.toString() + offset.toString()).toTypedArray()
        val sql = """
            SELECT c.tvg_id, c.name, c.group_title, c.logo, c.url, c.user_agent, c.referer
            FROM ${fromClause(mode)}
            $where
            ORDER BY ${orderClause(mode)}
            LIMIT ? OFFSET ?
        """.trimIndent()

        val result = ArrayList<Channel>(limit)
        db.rawQuery(sql, args).use { cursor ->
            while (cursor.moveToNext()) {
                result.add(
                    Channel(
                        name = cursor.getString(1),
                        group = cursor.getString(2),
                        logo = cursor.getString(3),
                        url = cursor.getString(4),
                        tvgId = cursor.getString(0),
                        userAgent = if (cursor.isNull(5)) null else cursor.getString(5),
                        referer = if (cursor.isNull(6)) null else cursor.getString(6),
                    )
                )
            }
        }
        return result
    }

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
                    bindNullable(insertChannel, 7, channel.userAgent)
                    bindNullable(insertChannel, 8, channel.referer)

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

    private fun buildFilter(group: String?, rawQuery: String): Pair<String, List<String>> {
        val clauses = ArrayList<String>(2)
        val args = ArrayList<String>(2)

        if (!group.isNullOrBlank()) {
            clauses.add("c.group_title = ?")
            args.add(group)
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
            // v2: favoritos e historico. O catalogo importado e preservado.
            if (oldVersion < 2) createPersonalTables(db)
        }

        override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
            db.execSQL("DROP TABLE IF EXISTS channels")
            db.execSQL("DROP TABLE IF EXISTS channel_groups")
            db.execSQL("DROP TABLE IF EXISTS meta")
            db.execSQL("DROP TABLE IF EXISTS favorites")
            db.execSQL("DROP TABLE IF EXISTS recent")
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
                    user_agent TEXT,
                    referer TEXT
                )
                """.trimIndent()
            )
            db.execSQL("CREATE UNIQUE INDEX idx_channels_url ON channels(url)")
            db.execSQL("CREATE INDEX idx_channels_name ON channels(name_key, id)")
            db.execSQL(
                "CREATE INDEX idx_channels_group_name ON channels(group_title, name_key, id)"
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
        }

        companion object {
            private const val DB_NAME = "catalog.db"
            private const val DB_VERSION = 2
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
                (tvg_id, name, name_key, group_title, logo, url, user_agent, referer)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        private const val PROGRESS_STEP = 5_000
        private const val MAX_RECENTS = 100
    }
}
