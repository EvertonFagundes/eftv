package com.eftv.android.cast

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * O relogio comum e o que mantem imagem e som juntos na TV: o celular carimba
 * as duas trilhas no mesmo instante e aqui cada amostra ganha um horario fixo.
 */
class PresentationClockTest {

    private val delayNs = 150_000_000L

    @Test
    fun `primeira amostra ancora depois do atraso inicial`() {
        val clock = PresentationClock(delayNs)
        val now = 5_000_000_000L

        assertEquals(now + delayNs, clock.schedule(1_000_000L, now))
    }

    @Test
    fun `amostras seguintes seguem o carimbo e nao o relogio local`() {
        val clock = PresentationClock(delayNs)
        val anchor = clock.schedule(1_000_000L, 5_000_000_000L)

        // 33,333 ms no carimbo = 33,333 ms na TV, mesmo que a rede tenha
        // atrasado a chegada desta amostra em 400 ms.
        val scheduled = clock.schedule(1_033_333L, 5_400_000_000L)

        assertEquals(anchor + 33_333_000L, scheduled)
    }

    @Test
    fun `carimbo anterior a ancora tambem e respeitado`() {
        val clock = PresentationClock(delayNs)
        val anchor = clock.schedule(1_000_000L, 5_000_000_000L)

        assertEquals(anchor - 20_000_000L, clock.schedule(980_000L, 5_000_000_000L))
    }

    @Test
    fun `reset faz a proxima amostra ancorar de novo`() {
        val clock = PresentationClock(delayNs)
        clock.schedule(1_000_000L, 5_000_000_000L)

        clock.reset()

        assertEquals(9_000_000_000L + delayNs, clock.schedule(7_000_000L, 9_000_000_000L))
    }

    @Test
    fun `atraso padrao e de 150 ms`() {
        assertEquals(150_000_000L, PresentationClock().schedule(0L, 0L))
    }
}
