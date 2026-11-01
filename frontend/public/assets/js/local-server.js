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
  const fmt = new Intl.NumberFormat("pt-BR");

  const secao = document.querySelector("[data-local-server]");
  if (!secao) return;

  const statusEl = document.querySelector("[data-local-status]");
  const redeEl = document.querySelector("[data-local-rede]");
  const lanEl = document.querySelector("[data-local-lan]");
  const btnIniciar = document.querySelector("[data-local-start]");
  const btnAbrir = document.querySelector("[data-local-open]");
  const btnParar = document.querySelector("[data-local-stop]");
  const btnInstalar = document.querySelector("[data-local-install]");
  const btnAndroid = document.querySelector("[data-local-android]");
  const btnExpand = document.querySelector("[data-local-expand]");
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
  let ultimoStatus = null;

  function status(texto, tom) {
    if (!statusEl) return;
    statusEl.textContent = texto;
    statusEl.dataset.tom = tom || "neutro";
  }

  function mostrar(el, visivel) {
    if (el) el.hidden = !visivel;
  }

  /* ------------------------------------------------- endereços de rede */
  let ultimaRedeHtml = null;

  function mostrarRede(urls) {
    if (!redeEl) return;
    const externos = (urls || []).filter((u) => !/127\.0\.0\.1|localhost/.test(u));
    if (!externos.length) {
      ultimaRedeHtml = null;
      redeEl.hidden = true;
      redeEl.textContent = "";
      return;
    }
    redeEl.hidden = false;
    const lista = externos
      .map((u) => `<code>${window.canaisEscape ? window.canaisEscape(u) : u}</code>`)
      .join(" · ");
    const html =
      "Na smart TV (na mesma rede Wi-Fi): " +
      lista +
      ' <button class="link-btn" type="button" data-copiar-rede>Copiar</button>' +
      "<small>Abra esse endereço no navegador da smart TV e salve como favorito: " +
      "da próxima vez é só um clique. Ele só vale enquanto as duas máquinas " +
      "estiverem na mesma rede.</small>" +
      `<small><strong>No aparelho que roda o servidor</strong> (celular ou notebook), ` +
      `use sempre <code>http://127.0.0.1:${porta}/</code>: esse endereço é o ` +
      "próprio aparelho e funciona no Wi-Fi e também nos dados móveis.</small>";

    // Só reescreve quando o conteúdo muda: a checagem periódica recriaria o
    // botão de copiar debaixo do dedo de quem estiver clicando.
    if (html === ultimaRedeHtml) return;
    ultimaRedeHtml = html;
    redeEl.innerHTML = html;
    const botao = redeEl.querySelector("[data-copiar-rede]");
    if (botao) {
      botao.addEventListener("click", () => {
        const texto = externos[0];
        const feito = () => {
          const antigo = botao.textContent;
          botao.textContent = "Copiado!";
          setTimeout(() => {
            botao.textContent = antigo;
          }, 1800);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(texto).then(feito, () => {});
          return;
        }
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
          // Sem área de transferência: o endereço fica visível para copiar.
        }
        area.remove();
      });
    }
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

  /* O servidor pode estar no MESMO aparelho que exibe a página (celular no
     Termux ou notebook). Quando o endereço da rede fica para trás — o aparelho
     saiu do Wi-Fi — o 127.0.0.1 continua de pé, inclusive nos dados móveis,
     porque o servidor escuta em 0.0.0.0 (que inclui o loopback). */
  async function sondarLoopback() {
    if (ehHostLocal || window.CANAIS_MODO !== "local") return null;
    const portas = [...new Set([Number(location.port) || 0, porta])].filter(
      (p) => p > 0
    );
    for (const p of portas) {
      try {
        const resp = await fetch(`http://127.0.0.1:${p}/api/status`, {
          cache: "no-store",
          mode: "cors",
        });
        if (!resp.ok) continue;
        const dados = await resp.json();
        if (dados && dados.ok) return { dados, porta: p };
      } catch (_) {
        // Tenta a próxima porta possível.
      }
    }
    return null;
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
      // Sem servidor o cartão inteiro volta a aparecer: é nele que está a explicação.
      if (secao) secao.classList.remove("is-compacto");
      mostrar(btnExpand, false);
      return;
    }
    mostrar(btnIniciar, false);
    mostrar(btnAbrir, true);
    if (btnAbrir) btnAbrir.href = `${enderecoLocal()}/`;
    const playlists = dados.playlists || 0;
    const canais = dados.canais || 0;
    ultimoStatus = dados;
    mostrarRede(dados.urls);

    // No modo local, quem já está com o servidor no ar não precisa do cartão
    // de apresentação: ele vira uma linha de status, com as opções atrás de
    // um botão discreto — a tela começa nos canais.
    const compacto =
      window.CANAIS_MODO === "local" && !!secao && !secao.dataset.expandido;
    if (secao) secao.classList.toggle("is-compacto", compacto);
    mostrar(btnExpand, compacto);

    // Quando a página é servida pelo próprio servidor, o endereço correto é o
    // que o navegador está usando (pode ser o IP da rede, em uma smart TV).
    const onde = ehHostLocal ? "" : " · você está em outro aparelho";
    status(
      `Servidor local ativo em ${enderecoLocal()} · ${fmt.format(playlists)} ${
        playlists === 1 ? "playlist" : "playlists"
      } · ${fmt.format(canais)} ${canais === 1 ? "canal" : "canais"}${onde}`,
      "ok"
    );
  }

  async function verificar() {
    const dados = await sondar();
    if (dados) {
      aplicarEstado(dados);
      return dados;
    }

    // O endereço da rede parou de responder. Se o servidor está neste mesmo
    // aparelho, o loopback segue no ar e é só voltar a usá-lo: ele vale no
    // Wi-Fi e também nos dados móveis.
    const local = await sondarLoopback();
    if (local) {
      const alvo = `http://127.0.0.1:${local.porta}/`;
      status(
        `Este endereço da rede não responde mais. Abrindo ${alvo} — ele funciona no Wi-Fi e nos dados móveis.`,
        "ok"
      );
      window.location.replace(alvo);
      return null;
    }

    aplicarEstado(null);
    if (window.CANAIS_MODO === "local") {
      status(
        ehHostLocal
          ? "O servidor local parou. Abra o Termux e rode \"eftv\" para voltar."
          : "Este endereço da rede não responde. No aparelho que roda o " +
              "servidor use http://127.0.0.1:" +
              porta +
              "/; na smart TV, confira se o servidor está ligado e na mesma rede Wi-Fi.",
        "erro"
      );
    }
    return null;
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
    const quer = `porta=${porta}` + (lanEl && lanEl.checked ? "&lan=1" : "");
    link.href = `eftv://iniciar?${quer}`;
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

    // O acesso pela rede só passa a valer quando o servidor sobe com --lan.
    lanEl &&
      lanEl.addEventListener("change", () => {
        if (!ultimoStatus) return;
        if (lanEl.checked && !ultimoStatus.rede) {
          status(
            "O servidor já está rodando só neste aparelho. Encerre-o " +
              "(botão \"Encerrar servidor\" ou fechando a janela do terminal) " +
              "e clique em \"Iniciar servidor local\" de novo.",
            "neutro"
          );
        }
      });

    // No Android não existe o protocolo eftv://: o servidor sobe pelo Termux.
    // O cartão de instalação (com o comando do Termux) só serve para quem
    // ainda não tem servidor: no modo local ele só empurrava os canais para
    // baixo, confundindo quem veio para assistir.
    if (ehAndroid) {
      mostrar(btnIniciar, false);
      mostrar(btnInstalar, false);
      const semServidor = window.CANAIS_MODO !== "local";
      mostrar(btnAndroid, semServidor);
      if (cardAndroid && semServidor) cardAndroid.hidden = false;
    }

    btnExpand &&
      btnExpand.addEventListener("click", () => {
        if (secao) secao.dataset.expandido = "1";
        if (secao) secao.classList.remove("is-compacto");
        mostrar(btnExpand, false);
      });

    // Mantém o estado em dia enquanto a página estiver aberta. É esta checagem
    // que devolve o aparelho para o 127.0.0.1 quando o endereço do Wi-Fi some
    // (troca para dados móveis) — vale nos dois modos.
    setInterval(() => {
      if (!iniciando) verificar();
    }, 15000);

    // Modo local: a própria página já é servida pelo server.py.
    if (window.CANAIS_MODO === "local") {
      secao.hidden = false;
      mostrar(btnIniciar, false);
      mostrar(btnAbrir, true);
      mostrar(btnParar, true);
      status("Verificando o servidor local...", "neutro");
      // O servidor responde com os números oficiais e os endereços de rede.
      // verificar() também recoloca o aparelho no 127.0.0.1 se o endereço da
      // rede tiver ficado para trás (celular que saiu do Wi-Fi).
      verificar();
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
