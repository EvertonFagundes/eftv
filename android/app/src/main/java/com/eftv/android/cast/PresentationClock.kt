package com.eftv.android.cast

/**
 * Relogio de apresentacao compartilhado entre video e audio na TV.
 *
 * O celular carimba as duas trilhas com o mesmo relogio (ver `CastSender`).
 * A primeira amostra que chega define a ancora:
 *
 * - `basePtsUs`: carimbo daquela amostra;
 * - `anchorNs`: instante local (nanoTime) em que ela deve aparecer, ja com um
 *   pequeno atraso para o buffer encher.
 *
 * A partir dai, toda amostra tem um horario absoluto previsivel:
 * `anchorNs + (pts - basePts)`. E isso que mantem labios e som juntos, mesmo
 * que a rede entregue os pacotes com jitter.
 */
class PresentationClock(
    /** Atraso inicial: da tempo de encher o buffer e evita engasgo no comeco. */
    private val startDelayNs: Long = 150_000_000L,
) {

    private val lock = Any()
    private var basePtsUs = 0L
    private var anchorNs = 0L
    private var started = false

    /** Instante (em `System.nanoTime`) em que a amostra [ptsUs] deve aparecer. */
    fun schedule(ptsUs: Long, nowNs: Long): Long = synchronized(lock) {
        if (!started) {
            basePtsUs = ptsUs
            anchorNs = nowNs + startDelayNs
            started = true
        }
        anchorNs + (ptsUs - basePtsUs) * 1_000L
    }

    /** Recomeca a contagem numa nova transmissao/reconexao. */
    fun reset() = synchronized(lock) {
        started = false
    }
}
