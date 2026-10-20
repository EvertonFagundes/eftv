/* EFTV - servidor local.
   A página (inclusive a versão do GitHub Pages) consegue iniciar o server.py
   do computador do usuário pelo protocolo eftv://, acompanhar o estado do
   servidor e abrir a versão completa em http://127.0.0.1:8124/.
   No modo local (servidor já no ar) este arquivo só mostra o status. */

(function () {
  const PORTA_PADRAO = 8124;
  const INTERVALO = 800;
  const TENTATIVAS = 75; // ~60 segundos
  const ABERTURA_OTIMISTA = 6000; // abre a aba local mesmo sem confirmar

  const secao = document.querySelector("[data-local-server]");
  if (!secao) return;

  const statusEl = document.querySelector("[data-local-status]");
  const btnIniciar = document.querySelector("[data-local-start]");
  const btnAbrir = document.querySelector("[data-local-open]");
  const btnParar = document.querySelector("[data-local-stop]");
  const btnInstalar = document.querySelector("[data-local-install]");
  const dialog = document.querySelector("[data-local-dialog]");
  const fecharDialog = document.querySelector("[data-local-dialog-close]");

  const porta = Number(secao.dataset.porta || PORTA_PADRAO) || PORTA_PADRAO;
  const base = `http://127.0.0.1:${porta}`;

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

  /* ------------------------------------------------------------- sondagem */
  async function sondar() {
    try {
      const resp = await fetch(`${base}/api/status`, { cache: "no-store", mode: "cors" });
      if (!resp.ok) return null;
      const dados = await resp.json();
      return dados && dados.ok ? dados : null;
    } catch (_) {
      return null;
    }
  }

  function aplicarEstado(dados) {
    if (!dados) {
      mostrar(btnIniciar, !iniciando);
      mostrar(btnAbrir, false);
      mostrar(btnParar, false);
      return;
    }
    mostrar(btnIniciar, false);
    mostrar(btnAbrir, true);
    if (btnAbrir) btnAbrir.href = `${base}/`;
    const playlists = dados.playlists || 0;
    const canais = dados.canais || 0;
    status(
      `Servidor local ativo em ${base} · ${playlists} ${
        playlists === 1 ? "playlist" : "playlists"
      } · ${canais} ${canais === 1 ? "canal" : "canais"}`,
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
    btnParar.disabled = true;
    status("Encerrando o servidor...", "neutro");
    try {
      await fetch(`${base}/api/servidor?acao=parar`, {
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

  /* ------------------------------------------------------------- início */
  function init() {
    if (btnAbrir) btnAbrir.href = `${base}/`;

    btnIniciar && btnIniciar.addEventListener("click", iniciar);
    btnParar && btnParar.addEventListener("click", parar);
    btnInstalar && btnInstalar.addEventListener("click", abrirDialog);
    fecharDialog && fecharDialog.addEventListener("click", fechar);

    // Modo local: a própria página já é servida pelo server.py.
    if (window.CANAIS_MODO === "local") {
      secao.hidden = false;
      mostrar(btnIniciar, false);
      mostrar(btnAbrir, true);
      mostrar(btnParar, true);
      status(`Servidor local ativo em ${base}.`, "ok");
      return;
    }

    secao.hidden = false;
    status("Verificando o servidor local...", "neutro");
    verificar().then((dados) => {
      if (!dados) {
        mostrar(btnIniciar, true);
        status("Servidor local parado. Inicie para usar a EFTV completa.", "neutro");
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
