package com.eftv.android

import android.app.Application
import android.os.Build
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.SvgDecoder
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.eftv.android.data.DeviceIdentity
import com.eftv.android.data.LogUtils
import com.eftv.android.data.api.EftvApi
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import timber.log.Timber
import java.util.concurrent.TimeUnit

class EftvApplication : Application(), ImageLoaderFactory {

    /**
     * O Coil nao decodifica SVG so por a dependencia estar no APK: precisa
     * registrar o decoder. Varias listas usam logo `.svg`, que sem isso cai
     * direto na capa gerada.
     */
    override fun newImageLoader(): ImageLoader =
        ImageLoader.Builder(this)
            .components { add(SvgDecoder.Factory()) }
            // O observador de rede do Coil pode deixar a fila parada quando o
            // Android reporta a rede como indisponivel (acontece em aparelhos
            // que bloqueiam o DNS do provedor). Os requests usam o proxy
            // local, que continua funcionando nesse cenario.
            .networkObserverEnabled(false)
            // Sem timeout o card fica preso no carregamento quando o servidor
            // aceita a conexao e nao responde. Com estes limites o fallback
            // (proxy local / capa gerada) entra em poucos segundos.
            .okHttpClient {
                OkHttpClient.Builder()
                    .connectTimeout(6, TimeUnit.SECONDS)
                    .readTimeout(8, TimeUnit.SECONDS)
                    .writeTimeout(8, TimeUnit.SECONDS)
                    .callTimeout(15, TimeUnit.SECONDS)
                    .build()
            }
            .build()

    override fun onCreate() {
        super.onCreate()

        // Log sempre, inclusive no APK de release: sem isso um problema no
        // aparelho do cliente ("nao conecta", "fecha sozinho") chega sem
        // nenhuma pista. O logcat e privado desde o Android 4.1: outro app nao
        // le; so o usuario via depuracao USB.
        Timber.plant(Timber.DebugTree())

        installCrashReporter()

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        EftvServerService.start(this)
    }

    /**
     * Envia travamentos para o backend antes de o app fechar.
     *
     * Sem isso, "o app fechou sozinho" chegava por WhatsApp sem nenhuma pista
     * de versao, aparelho ou causa. O envio roda em thread propria com espera
     * curta: nao atrasa o fechamento nem substitui o handler do sistema.
     */
    private fun installCrashReporter() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching { reportCrash(throwable) }
            previous?.uncaughtException(thread, throwable)
        }
    }

    private fun reportCrash(throwable: Throwable) {
        val device = DeviceIdentity(this)
        val api = EftvApi(deviceId = device.id, deviceName = device.name)
        val sender = Thread {
            runCatching {
                runBlocking {
                    api.reportCrash(
                        // Um crash ao abrir um canal pode carregar a URL do
                        // stream (com usuário/senha) na mensagem: o relatório
                        // enviado ao backend vai sempre mascarado.
                        message = LogUtils.redactText(throwable.toString()),
                        stacktrace = LogUtils.redactThrowable(throwable),
                        appVersion = BuildConfig.VERSION_NAME,
                        device = device.name,
                        android = Build.VERSION.RELEASE.orEmpty(),
                    )
                }
            }
        }
        sender.start()
        // No maximo 2s: o relato sai antes de o processo ser encerrado.
        runCatching { sender.join(2_000) }
    }
}
