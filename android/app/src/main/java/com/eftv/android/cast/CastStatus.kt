package com.eftv.android.cast

/** Estado da transmissao, compartilhado entre o servico e a tela. */
data class CastStatus(
    val state: State,
    val message: String = "",
) {
    enum class State { IDLE, CONNECTING, STREAMING, ERROR }

    val isActive: Boolean
        get() = state == State.CONNECTING || state == State.STREAMING

    companion object {
        val IDLE = CastStatus(State.IDLE)
    }
}
