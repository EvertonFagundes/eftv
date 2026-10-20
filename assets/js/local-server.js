/* EFTV - servidor local.
   A página (inclusive a versão do GitHub Pages) consegue iniciar o server.py
   do computador do usuário pelo protocolo eftv://, acompanhar o estado do
   servidor e abrir a versão completa em http://127.0.0.1:8124/.
   No Android, o servidor roda pelo Termux e a página mostra o passo a passo.
   No modo local (servidor já no ar) este arquivo só mostra o status. */

(function () {
  const PORTA_PADRAO = 8124;
  const INTERVALO = 800;
  const TENTATIVAS = 75; // ~60 segundos
  const ABERTURA_OTIMISTA = 6000; // abre a aba local mesmo sem confirmar

  const secao = document.querySelector("[data-local-server]");
  if (!secao) return;

  const statusEl = document.querySelector("[data-local-status]");
  const redeEl = document.querySelector("[data-local-rede]");
  const btnIniciar = document.querySelector("[data-local-start]");
  const btnAbrir = document.querySelector("[data-local-open]");
  const btnParar = document.querySelector("[data-local-stop]");
  const btnInstalar = document.querySelector("[data-local-install]");
  const btnAndroid = document.querySelector("[data-local-android]");
  const dialog = document.querySelector("[data-local-dialog]");
  const fecharDialog = document.querySelector("[data-local-dialog-close]");

  const cardAndroid = document.querySelector("[data-android-card]");
  const btnCopiar = document.querySelector("[data-copiar-comando]");
  const btnTermux = document.querySelector("[data-abrir-termux]");
  const comandoEl = document.querySelector("[data-android-comando]");

  const porta = Number(secao.dataset.porta || PORTA_PADRAO) || PORTA_PADRAO;
  const base = `http://127.0.0.1:${porta}`;
  const ehAndroid = /Android/i.test(navigator.userAgent);
  const ehHostLocal = /^(127\.0\.0\.1|localhost|::1)$/i.test(location.hostname);

  let aba = null;
  let iniciando = false;
  let abaAberta = false;

  function status(texto, tom) {
    if (!statusEl) return;
    statusEl.textContent = texto;
    statusEl.dataset.tom = tom || "neutro";
  }

  function mostrar(el, visivel) {
    if (el) el.hidden = !visivel;
  }

  /* ------------------------------------------------- endereços de rede */
  function mostrarRede(urls) {
    if (!redeEl) return;
    const externos = (urls || []).filter((u) => !/127\.0\.0\.1|localhost/.test(u));
    if (!externos.length) {
      redeEl.hidden = true;
      redeEl.textContent = "";
      return;
    }
    redeEl.hidden = false;
    redeEl.innerHTML =
      "Outros aparelhos na mesma rede: " +
      externos
        .map((u) => `<code>${window.canaisEscape ? window.canaisEscape(u) : u}</code>`)
        .join(" · ");
  }

  /* ------------------------------------------------------------- sondagem */
  async function sondar() {
    // No modo local a consulta é feita no mesmo servidor que serve a página
    // (assim funciona também de uma smart TV, que não tem o 127.0.0.1 do
    // celular). No modo estático, sondamos o loopback da própria máquina.
    const url =
      window.CANAIS_MODO === "local" ? "/api/status" : `${base}/api/status`;
    try {
      const resp = await fetch(url, { cache: "no-store", mode: "cors" });
      if (!resp.ok) return null;
      const dados = await resp.json();
      return dados && dados.ok ? dados : null;
    } catch (_) {
      return null;
    }
  }

  function enderecoLocal() {
    return window.CANAIS_MODO === "local" ? location.origin : base;
  }

  function aplicarEstado(dados) {
    if (!dados) {
      mostrar(btnIniciar, !iniciando);
      mostrar(btnAbrir, false);
      mostrar(btnParar, false);
      mostrarRede([]);
      return;
    }
    mostrar(btnIniciar, false);
    mostrar(btnAbrir, true);
    if (btnAbrir) btnAbrir.href = `${enderecoLocal()}/`;
    const playlists = dados.playlists || 0;
    const canais = dados.canais || 0;
    mostrarRede(dados.urls);

    // Quando a página é servida pelo próprio servidor, o endereço correto é o
    // que o navegador está usando (pode ser o IP da rede, em uma smart TV).
    const onde = ehHostLocal ? "" : " · você está em outro aparelho";
    status(
      `Servidor local ativo em ${enderecoLocal()} · ${playlists} ${
        playlists === 1 ? "playlist" : "playlists"
      } · ${canais} ${canais === 1 ? "canal" : "canais"}${onde}`,
      "ok"
    );
  }

  async function verificar() {
    const dados = await sondar();
    aplicarEstado(dados);
    return dados;
  }

  /* -------------------------------------------------------------- início */
  function abrirAbaLocal() {
    abaAberta = true;
    if (aba && !aba.closed) {
      aba.location.href = `${base}/`;
      return;
    }
    window.open(`${base}/`, "_blank", "noopener");
  }

  function fecharAba() {
    if (abaAberta || !aba) return;
    try {
      aba.close();
    } catch (_) {
      // A aba pode ter sido bloqueada pelo navegador. Sem problema.
    }
  }

  function aguardarServidor() {
    let tentativas = 0;
    const inicio = Date.now();
    const timer = setInterval(async () => {
      tentativas += 1;
      const dados = await sondar();
      if (dados) {
        clearInterval(timer);
        iniciando = false;
        aplicarEstado(dados);
        abrirAbaLocal();
        return;
      }
      const decorrido = Date.now() - inicio;
      if (!abaAberta && decorrido > ABERTURA_OTIMISTA) {
        // Abertura otimista: o servidor já teve tempo de subir.
        abrirAbaLocal();
      }
      if (tentativas === 12) {
        status(
          "Ainda não respondeu. Se o navegador perguntou sobre o aplicativo EFTV, confirme a abertura.",
          "neutro"
        );
      }
      if (tentativas >= TENTATIVAS) {
        clearInterval(timer);
        iniciando = false;
        fecharAba();
        mostrar(btnIniciar, true);
        status(
          "Não foi possível iniciar o servidor. Instale o lançador da EFTV e tente de novo.",
          "erro"
        );
        abrirDialog();
      }
    }, INTERVALO);
  }

  function iniciar() {
    if (iniciando) return;
    iniciando = true;
    mostrar(btnIniciar, false);
    status("Iniciando o servidor local...", "ok");

    // Abre a aba antes do processo assíncrono para não ser bloqueada pelo
    // bloqueador de pop-ups do navegador.
    try {
      aba = window.open("about:blank", "_blank");
    } catch (_) {
      aba = null;
    }

    // Dispara o protocolo registrado pelo lançador.
    const link = document.createElement("a");
    link.href = `eftv://iniciar?porta=${porta}`;
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();

    aguardarServidor();
  }

  /* -------------------------------------------------------------- parar */
  async function parar() {
    if (!btnParar) return;
    const aviso =
      "Encerrar o servidor local?\n\n" +
      "Os canais param de tocar e a página precisa ser recarregada. " +
      "Para voltar, use o botão \"Iniciar servidor local\".";
    if (!window.confirm(aviso)) return;
    btnParar.disabled = true;
    status("Encerrando o servidor...", "neutro");
    // No modo local o comando vai para o servidor que serve a página.
    const url =
      window.CANAIS_MODO === "local"
        ? "/api/servidor?acao=parar"
        : `${base}/api/servidor?acao=parar`;
    try {
      await fetch(url, {
        method: "POST",
        headers: { "X-EFTV-Local": "1" },
        cache: "no-store",
      });
      status("Servidor encerrado. Feche esta janela se quiser sair.", "ok");
      mostrar(btnParar, false);
      mostrar(btnAbrir, false);
      mostrar(btnIniciar, true);
    } catch (_) {
      status("Não foi possível encerrar o servidor.", "erro");
    } finally {
      btnParar.disabled = false;
    }
  }

  /* ------------------------------------------------------------- diálogo */
  function abrirDialog() {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "open");
  }

  function fechar() {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  /* -------------------------------------------------------------- Android */
  function mostrarCardAndroid() {
    if (!cardAndroid) return;
    cardAndroid.hidden = false;
    cardAndroid.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function copiarComando() {
    if (!comandoEl || !btnCopiar) return;
    const texto = (comandoEl.textContent || "").trim();
    const feito = () => {
      const antigo = btnCopiar.textContent;
      btnCopiar.textContent = "Copiado!";
      setTimeout(() => {
        btnCopiar.textContent = antigo;
      }, 1800);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(feito, () => {});
      return;
    }
    // Fallback para navegadores sem API de área de transferência.
    const area = document.createElement("textarea");
    area.value = texto;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      feito();
    } catch (_) {
      // Sem área de transferência: o comando fica visível para copiar à mão.
    }
    area.remove();
  }

  function abrirTermux() {
    // Intent do Android: abre o Termux instalado no aparelho.
    window.location.href = "intent://#Intent;package=com.termux;end";
  }

  /* ------------------------------------------------------------- início */
  function init() {
    if (btnAbrir) btnAbrir.href = `${enderecoLocal()}/`;

    btnIniciar && btnIniciar.addEventListener("click", iniciar);
    btnParar && btnParar.addEventListener("click", parar);
    btnInstalar && btnInstalar.addEventListener("click", abrirDialog);
    btnAndroid && btnAndroid.addEventListener("click", mostrarCardAndroid);
    fecharDialog && fecharDialog.addEventListener("click", fechar);
    btnCopiar && btnCopiar.addEventListener("click", copiarComando);
    btnTermux && btnTermux.addEventListener("click", abrirTermux);

    // No Android não existe o protocolo eftv://: o servidor sobe pelo Termux.
    if (ehAndroid) {
      mostrar(btnIniciar, false);
      mostrar(btnInstalar, false);
      mostrar(btnAndroid, true);
      if (cardAndroid) cardAndroid.hidden = false;
    }

    // Modo local: a própria página já é servida pelo server.py.
    if (window.CANAIS_MODO === "local") {
      secao.hidden = false;
      mostrar(btnIniciar, false);
      mostrar(btnAbrir, true);
      mostrar(btnParar, true);
      const onde = ehHostLocal ? "" : " · você está em outro aparelho";
      status(`Servidor local ativo em ${location.origin}${onde}`, "ok");
      // O servidor responde com os números oficiais e os endereços de rede.
      sondar().then((dados) => {
        if (dados) aplicarEstado(dados);
      });
      return;
    }

    secao.hidden = false;
    status("Verificando o servidor local...", "neutro");
    verificar().then((dados) => {
      if (!dados) {
        mostrar(btnIniciar, !ehAndroid);
        status(
          "Servidor local parado. Sem ele os canais não tocam: o navegador " +
            "bloqueia os streams (CORS). Use o servidor local.",
          "erro"
        );
      }
    });

    // Mantém o estado em dia enquanto a página estiver aberta.
    setInterval(() => {
      if (!iniciando) verificar();
    }, 15000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
