package com.eftv.android.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Escopo de corrotinas que vive enquanto o aplicativo estiver vivo.
 *
 * Usado para tarefas que precisam terminar mesmo depois que a Activity
 * responsavel foi destruida (por exemplo, salvar o progresso de um filme
 * quando o usuario fecha o player). Se usarmos o `lifecycleScope` da Activity,
 * o trabalho seria cancelado no `onDestroy` e a gravacao aconteceria na
 * thread principal, travando a interface.
 */
object AppScope {

    val io: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
}
