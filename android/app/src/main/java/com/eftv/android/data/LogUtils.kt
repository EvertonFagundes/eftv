package com.eftv.android.data

import java.net.URI

/**
 * Utilidades para não vazar credenciais em logs, telas de erro e links.
 *
 * Playlists IPTV costumam carregar usuário/senha na própria URL
 * (`.../live/usuario/senha/123.ts` ou `?username=...&password=...`). Escrever
 * essa URL inteira no logcat, num relatório de erro ou na tela deixa a
 * credencial visível para quem tiver acesso ao aparelho.
 */
object LogUtils {

    /**
     * Versão segura para exibição: mantém esquema, host, porta e a extensão do
     * arquivo (útil para saber se era .ts, .m3u8, .mpd), mas esconde caminho e
     * parâmetros.
     */
    fun redactUrl(raw: String?): String {
        if (raw.isNullOrBlank()) return ""
        return try {
            val uri = URI(raw.trim())
            val scheme = uri.scheme?.lowercase().orEmpty()
            if (scheme.isBlank() || uri.host.isNullOrBlank()) return "…"

            val porta = if (uri.port > 0) ":${uri.port}" else ""
            val arquivo = uri.path.orEmpty().substringAfterLast('/')
            val extensao = arquivo.substringAfterLast('.', "")
            val sufixo = if (extensao.isNotEmpty() && extensao.length <= 5) ".$extensao" else ""
            val consulta = if (!uri.rawQuery.isNullOrEmpty()) "?…" else ""
            "$scheme://${uri.host}$porta/…$sufixo$consulta"
        } catch (_: Exception) {
            // URL inválida ou com caracteres que o URI não aceita: não arrisca.
            "…"
        }
    }

    private val URL_NO_TEXTO = Regex("""https?://[^\s"'<>]+""", RegexOption.IGNORE_CASE)

    /** Troca qualquer URL embutida num texto (mensagem de erro, stack trace). */
    fun redactText(texto: String?): String {
        if (texto.isNullOrBlank()) return texto.orEmpty()
        return URL_NO_TEXTO.replace(texto) { achado ->
            val bruto = achado.value.trimEnd('.', ',', ';', ')', ']', '}')
            val resto = achado.value.substring(bruto.length)
            redactUrl(bruto) + resto
        }
    }

    /** Stack trace seguro para logcat e relatório de crash. */
    fun redactThrowable(erro: Throwable?): String {
        if (erro == null) return ""
        return redactText(erro.stackTraceToString())
    }

    /** Só aceita atualização por HTTPS em host público. */
    fun isSafeUpdateUrl(raw: String?): Boolean {
        if (raw.isNullOrBlank()) return false
        return try {
            val uri = URI(raw.trim())
            if (!uri.scheme.equals("https", ignoreCase = true)) return false
            if (uri.host.isNullOrBlank()) return false
            if (!uri.userInfo.isNullOrBlank()) return false

            val host = uri.host.lowercase().removePrefix("[").removeSuffix("]")
            if (host == "localhost" || host == "::1" || host.endsWith(".local")) return false
            if (host == "0.0.0.0") return false

            // Faixas privadas e link-local em IPv4.
            val partes = host.split(".")
            if (partes.size == 4 && partes.all { it.toIntOrNull() != null }) {
                val a = partes[0].toInt()
                val b = partes[1].toInt()
                if (a == 10 || a == 127) return false
                if (a == 169 && b == 254) return false
                if (a == 172 && b in 16..31) return false
                if (a == 192 && b == 168) return false
            }
            true
        } catch (_: Exception) {
            false
        }
    }
}
