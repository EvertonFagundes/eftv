package com.eftv.android.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.eftv.android.data.api.EftvApi
import timber.log.Timber
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Sessao do assinante salva localmente. O token de acesso e curto (15 min por
 * padrao) e o refresh token permite renovar sem pedir a senha de novo.
 *
 * Os tokens ficam cifrados com uma chave AES/GCM do Android Keystore, que so
 * existe neste aparelho. Antes iam em texto puro no SharedPreferences: quem
 * tinha acesso ao arquivo (root, backup, APK de "cliente" modificado) podia
 * copiar a sessao e usar a mesma assinatura em outro lugar. Valores gravados
 * por versoes antigas continuam sendo lidos e sao migrados no primeiro uso.
 */
class SessionStore(context: Context) {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** A migracao de tokens antigos roda uma vez por instancia. */
    @Volatile
    private var legacyChecked = false

    /** Chave do Keystore; null quando o aparelho nao oferece Keystore. */
    private val key: SecretKey? by lazy {
        runCatching { loadOrCreateKey() }
            .onFailure { Timber.w(it, "Keystore indisponivel; sessao sem cifra") }
            .getOrNull()
    }

    fun save(tokens: EftvApi.TokenPair, email: String, emailVerified: Boolean = false) {
        val expiresAt = System.currentTimeMillis() +
            (tokens.expiresInSeconds * 1000L) - EXPIRY_MARGIN_MS
        prefs.edit()
            .putString(KEY_ACCESS, protect(tokens.accessToken))
            .putString(KEY_REFRESH, protect(tokens.refreshToken))
            .putString(KEY_EMAIL, email)
            .putBoolean(KEY_EMAIL_VERIFIED, emailVerified)
            .putLong(KEY_EXPIRES_AT, expiresAt)
            .apply()
    }

    fun accessToken(): String? {
        migrateLegacyTokens()
        return reveal(prefs.getString(KEY_ACCESS, null))
    }

    fun refreshToken(): String? {
        migrateLegacyTokens()
        return reveal(prefs.getString(KEY_REFRESH, null))
    }

    fun email(): String? = prefs.getString(KEY_EMAIL, null)

    fun isEmailVerified(): Boolean = prefs.getBoolean(KEY_EMAIL_VERIFIED, false)

    fun hasSession(): Boolean = !accessToken().isNullOrBlank()

    fun isAccessTokenExpired(now: Long = System.currentTimeMillis()): Boolean =
        prefs.getLong(KEY_EXPIRES_AT, 0L) <= now

    fun clear() {
        prefs.edit().clear().apply()
    }

    fun setEmailVerified(verified: Boolean) {
        prefs.edit().putBoolean(KEY_EMAIL_VERIFIED, verified).apply()
    }

    // ------------------------------------------------------------------
    // Cifra dos tokens
    // ------------------------------------------------------------------

    /**
     * Cifra um token. Se o Keystore falhar (aparelho sem suporte, chave
     * invalidada), grava em texto puro para o cliente nao perder a sessao.
     */
    private fun protect(value: String): String {
        if (value.isBlank()) return ""
        val secret = key ?: return value
        return runCatching {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, secret)
            val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
            val payload = cipher.iv + encrypted
            PREFIX + Base64.encodeToString(payload, Base64.NO_WRAP)
        }.getOrElse {
            Timber.w(it, "Falha ao cifrar a sessao; usando texto puro")
            value
        }
    }

    /** Le um token cifrado (ou em texto puro, de versao antiga). */
    private fun reveal(stored: String?): String? {
        if (stored.isNullOrBlank()) return null
        if (!stored.startsWith(PREFIX)) return stored

        val secret = key ?: return null
        return runCatching {
            val payload = Base64.decode(stored.removePrefix(PREFIX), Base64.NO_WRAP)
            if (payload.size <= IV_SIZE) error("Token cifrado invalido")
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                secret,
                GCMParameterSpec(TAG_BITS, payload, 0, IV_SIZE),
            )
            String(cipher.doFinal(payload, IV_SIZE, payload.size - IV_SIZE), Charsets.UTF_8)
        }.getOrElse {
            // Chave trocada/apagada: a sessao antiga nao pode mais ser usada.
            Timber.w(it, "Nao foi possivel ler a sessao salva")
            prefs.edit().remove(KEY_ACCESS).remove(KEY_REFRESH).apply()
            null
        }
    }

    /** Converte tokens em texto puro (versoes <= 1.4.8) para o formato cifrado. */
    private fun migrateLegacyTokens() {
        if (legacyChecked) return
        legacyChecked = true

        val access = prefs.getString(KEY_ACCESS, null)
        val refresh = prefs.getString(KEY_REFRESH, null)
        val legacyAccess = !access.isNullOrBlank() && !access.startsWith(PREFIX)
        val legacyRefresh = !refresh.isNullOrBlank() && !refresh.startsWith(PREFIX)
        if (!legacyAccess && !legacyRefresh) return

        val editor = prefs.edit()
        if (legacyAccess) editor.putString(KEY_ACCESS, protect(access.orEmpty()))
        if (legacyRefresh) editor.putString(KEY_REFRESH, protect(refresh.orEmpty()))
        editor.apply()
    }

    private fun loadOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)
            ?.let { return it.secretKey }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    private companion object {
        const val PREFS = "eftv_session"
        const val KEY_ACCESS = "access_token"
        const val KEY_REFRESH = "refresh_token"
        const val KEY_EMAIL = "email"
        const val KEY_EMAIL_VERIFIED = "email_verified"
        const val KEY_EXPIRES_AT = "expires_at"

        const val KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "eftv_session_key"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val PREFIX = "v1:"
        const val IV_SIZE = 12
        const val TAG_BITS = 128

        /** Renova um pouco antes de expirar, para nao falhar no meio do uso. */
        const val EXPIRY_MARGIN_MS = 30_000L
    }
}
