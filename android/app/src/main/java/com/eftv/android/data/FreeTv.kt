package com.eftv.android.data

/**
 * Categoria virtual "Abertos": canais de TV aberta que o provedor espalha em
 * grupos diferentes ("Canais | Globos Sudeste", "Canais | RecordTV"...).
 *
 * O cliente procura "Globo" pensando em canal aberto, nao em "Globos Sudeste".
 * Estes canais continuam nas categorias originais e passam a aparecer tambem em
 * Abertos - a lista e filtrada pelo nome, nao pelo grupo da playlist.
 */
object FreeTv {

    /** Identificador reservado: nunca colide com um group_title real. */
    const val GROUP = "\u0001abertos"

    private data class Rule(val pattern: String, val excludes: List<String> = emptyList())

    /**
     * Nomes que identificam emissoras abertas.
     *
     * As exclusoes evitam os canais pagos da mesma familia: GloboNews,
     * Globoplay e Premiere nao sao TV aberta; Band Sports e Band News tambem
     * nao. `name_key` no banco ja vem sem acento e em minusculas.
     */
    private val RULES = listOf(
        Rule("globo", listOf("globonews", "globoplay", "premiere", "telecine", "canal globo")),
        Rule("record"),
        Rule("sbt"),
        Rule(
            "band",
            listOf("bandsports", "band sports", "bandnews", "band news", "band play"),
        ),
        Rule("redetv"),
        Rule("rede tv"),
        Rule("cultura"),
        Rule("tv brasil"),
        Rule("gazeta"),
        Rule("aparecida"),
        Rule("cancaonova"),
        Rule("canção nova"),
        Rule("rede vida"),
        Rule("loading"),
        Rule("ideal tv"),
        Rule("futura"),
        Rule("tv senado"),
        Rule("tv camara"),
        Rule("tv justica"),
        Rule("tv assembleia"),
        Rule("record news"),
    )

    /**
     * Clausula SQL que seleciona os canais abertos, com os argumentos na ordem.
     *
     * Inclui tambem o que a propria playlist ja marcou como aberto
     * (`group_key LIKE %aberto%`), para nao perder emissora local que nao esta
     * na lista de nomes.
     */
    fun clause(): Pair<String, List<String>> {
        val parts = ArrayList<String>()
        val args = ArrayList<String>()

        for (rule in RULES) {
            val sql = StringBuilder("c.name_key LIKE ?")
            args.add("%${rule.pattern}%")
            for (exclude in rule.excludes) {
                sql.append(" AND c.name_key NOT LIKE ?")
                args.add("%$exclude%")
            }
            parts.add("($sql)")
        }
        parts.add("c.group_key LIKE ?")
        args.add("%aberto%")

        return "(${parts.joinToString(" OR ")})" to args
    }
}
