> **HISTÓRICO**: este documento descreve a versão antiga (Chaquopy + aiohttp +
> WebView). O app atual é nativo, com lista de canais e ExoPlayer — veja
> `README.md`. O código antigo foi movido para `legacy/`.

# EFTV-Android — diagnóstico e correções

## Causas reais do "não funcionou"

### 1. `aiohttp` nunca foi instalado no APK (causa do `ModuleNotFoundError`)
No Chaquopy **não existe instalação automática a partir de `src/main/python/requirements.txt`**.
O `build.gradle.kts` não tinha nenhum bloco `pip`, então o APK saía só com
`server_android.py` e `requirements.txt`. Comprovação: `app/build/pip/` estava vazio e o
`assets/chaquopy/app.imy` do APK não continha `aiohttp`.

Correção: bloco `chaquopy { defaultConfig { pip { install("-r", "...") } } }`.

### 2. Chaquopy 13.0.0 é incompatível com AGP 8.5
Pela tabela oficial, Chaquopy 13.0 suporta AGP **4.1–7.3**. O projeto usava AGP 8.5.
Além disso, Chaquopy 13 só tem Python até **3.11**, e a máquina de build só tem **3.12**
(o que impede o pip de rodar).

Correção: Chaquopy **15.0.1** (AGP 7.0–8.5, Python 3.8–3.12) + `version = "3.12"`.

### 2.1. `aiohttp==3.9.5` não tem wheel para `cp312`/Android
O índice do Chaquopy (`https://chaquo.com/pypi-13.1`) só disponibiliza wheel
nativo de `aiohttp` para CPython 3.12 na versão **3.9.1** (arm64-v8a e x86_64).
Com a 3.9.5 o pip baixa o sdist e tenta compilar C, e o Chaquopy aborta com
`Chaquopy_cannot_compile_native_code`.

Correção: pin `aiohttp==3.9.1` em `app/src/main/python/requirements.txt`.

### 3. `start_server()` era `async def` e o Kotlin chamava com `callAttr`
`callAttr` em uma função `async def` retorna um objeto *coroutine* que **nunca é
executado**. Resultado: nenhum servidor subia, sem erro visível.

Correção: `start_server()`/`stop_server()` agora são funções síncronas que criam o
event loop asyncio numa thread dedicada e só retornam quando a porta está ouvindo.

### 4. WebView carregava um arquivo que não existe
`webView.loadUrl("file:///android_asset/www/index.html")`, mas `assets/www/` estava
vazio → tela branca / `ERR_FILE_NOT_FOUND`.

Correção: WebView carrega `http://127.0.0.1:8124/` **depois** de confirmar `/health`.
Em erro, mostra uma página de diagnóstico com botão "Tentar novamente".

### 5. Serviço em processo separado duplicaria o Python
`android:process=":python"` no `PythonService`, que nunca era iniciado pela Activity.
Se fosse iniciado, um segundo interpretador tentaria abrir a mesma porta 8124.

Correção: serviço no mesmo processo e `start_server` idempotente.

### 6. ABIs incompatíveis com Python 3.12
Python 3.12+ no Chaquopy só existe em 64 bits. `armeabi-v7a` e `x86` foram removidos
(ficaram `arm64-v8a` e `x86_64`).

## Versões efetivas do APK

| Componente | Versão |
|---|---|
| Chaquopy | 15.0.1 |
| Python (runtime/build) | 3.12 |
| aiohttp | 3.9.1 |
| AGP | 8.5.0 |
| Kotlin | 1.9.22 |
| JDK (build) | 21 |
| minSdk / targetSdk | 24 / 34 |
| ABIs | arm64-v8a, x86_64 |

## Status

Build validado: `BUILD SUCCESSFUL`.

- APK: `app/build/outputs/apk/debug/app-debug.apk` (~41 MB)
- `assets/chaquopy/requirements-*.imy` contém `aiohttp 3.9.1` + nativos
  (`frozenlist`, `multidict`, `yarl`) para arm64-v8a e x86_64
- `assets/chaquopy/app.imy` contém `server_android.pyc` (Python 3.12)
- Ciclo `start_server` → `/health` → `stop_server` → restart testado no PC
  com aiohttp 3.9.1 + Python 3.12.3

## Como testar no celular

```bash
# instalar
adb install -r app/build/outputs/apk/debug/app-debug.apk

# logs do app + Python + Chaquopy
adb logcat -c
adb logcat | grep -Ei "EFTV|python|chaquopy|AndroidRuntime"
```

Endpoints para conferir no navegador do próprio celular:

- http://127.0.0.1:8124/health
- http://127.0.0.1:8124/api/status
- http://127.0.0.1:8124/player.html  (stream HLS de demonstração)

Inspeção da WebView em build debug: `chrome://inspect` no Chrome do PC com o celular
conectado (o app habilita `setWebContentsDebuggingEnabled` em debug).

## Teste do servidor Python no PC (sem Android)

```bash
python3 -m venv /tmp/eftv && /tmp/eftv/bin/pip install -r app/src/main/python/requirements.txt
/tmp/eftv/bin/python app/src/main/python/server_android.py
# abra http://127.0.0.1:8124
```
