/* EFTV - página de canal.
   Monta o cabeçalho do canal, o painel do player (iframe), o seletor de
   transmissão, o modo tela ampla e a barra lateral de programação. */

(function () {
  const params = new URLSearchParams(location.search);
  const slug = params.get("c") || "";

  function mostrarNaoEncontrado() {
    document.title = "Canal não encontrado — EFTV";
    const main = document.querySelector("main");
    if (!main) return;
    main.innerHTML = `
      <section class="not-found">
        <span class="eyebrow">EFTV</span>
        <h1>Canal não encontrado</h1>
        <p>Esse canal não está na sua biblioteca. Volte para a página inicial e escolha um canal importado.</p>
        <a class="btn btn-primary" href="index.html">Voltar para os canais</a>
      </section>`;
  }

  async function iniciar() {
    const canal = window.CanaisAPI ? window.CanaisAPI.porSlug(slug) : null;
    if (!canal) {
      mostrarNaoEncontrado();
      return;
    }

    // No servidor local as fontes de transmissão não vêm no catálogo: ele
    // pode ter dezenas de milhares de canais e carregaria URLs demais.
    // Elas chegam aqui sob demanda, só quando a página do canal é aberta.
    // No modo estático (GitHub Pages) as fontes já são montadas no navegador.
    if (
      (!canal.fontes || !canal.fontes.length) &&
      window.CANAIS_MODO === "local"
    ) {
      try {
        const resp = await fetch("/api/canal?slug=" + encodeURIComponent(slug), {
          cache: "no-store",
        });
        if (resp.ok) {
          const dados = await resp.json();
          if (dados && dados.ok && dados.canal) Object.assign(canal, dados.canal);
        }
      } catch (_) {
        // Sem detalhe: a página continua mostrando o que já tem.
      }
    }

    const fontes = Array.isArray(canal.fontes) ? canal.fontes : [];
    const aoVivo = canal.aoVivo !== false;
    const esc = window.canaisEscape || ((v) => String(v));

    function preencherCabecalho() {
      document.title = `${canal.nome} ${aoVivo ? "ao vivo" : "sob demanda"} — EFTV`;
      const set = (sel, txt) => {
        const el = document.querySelector(sel);
        if (el) el.textContent = txt;
      };
      set("[data-canal-nome]", canal.nome);
      set("[data-canal-nome-mini]", canal.nome);
      set("[data-canal-nome-mini2]", canal.nome);
      const categoriaBase = window.CanaisAPI.categoriaNome(canal.categoria);
      const grupo = String(canal.grupo || "")
        .replace(/^(canais?|filmes?|s[eé]ries?)\s*\|\s*/i, "")
        .replace(/\[[^\]]*\]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      const chave = (valor) =>
        (window.canaisNormalize ? window.canaisNormalize(valor) : valor).replace(/s$/, "");
      set(
        "[data-canal-categoria]",
        grupo && chave(grupo) !== chave(categoriaBase)
          ? `${categoriaBase} · ${grupo}`
          : categoriaBase
      );
      set("[data-canal-nome-breadcrumb]", canal.nome);
      set("[data-canal-opcoes]", `${fontes.length} ${fontes.length > 1 ? "opções" : "opção"} de transmissão`);

      const flag = document.querySelector("[data-canal-live-flag]");
      if (flag) {
        flag.innerHTML = `<i class="live-dot"></i> ${aoVivo ? "Canal ao vivo agora" : "Conteúdo sob demanda"}`;
        flag.classList.toggle("is-vod", !aoVivo);
      }
      const chip = document.querySelector("[data-canal-live-chip]");
      if (chip) {
        chip.innerHTML = `<i class="live-dot"></i> ${aoVivo ? "AO VIVO" : "SOB DEMANDA"}`;
        chip.classList.toggle("is-vod", !aoVivo);
      }
      set("[data-canal-live-sub]", aoVivo ? "Transmissão ao vivo" : "Vídeo sob demanda");

      const logo = document.querySelector("[data-canal-logo]");
      if (logo) {
        logo.src = canal.logo || "assets/img/eftv-mark.svg";
        logo.alt = canal.nome;
        logo.onerror = () => {
          logo.replaceWith(Object.assign(document.createElement("div"), { textContent: canal.nome }));
        };
      }

      const agoraInfo = canal.agora || {};
      const agora = document.querySelector("[data-programa-agora]");
      if (agora) {
        agora.innerHTML =
          `<div class="program-tag"><i></i> ${aoVivo ? "NO AR AGORA" : "SOB DEMANDA"}</div>` +
          `<h2>${esc(agoraInfo.titulo || canal.nome)}</h2>` +
          `<small>${aoVivo ? `Hoje, das ${esc(agoraInfo.inicio || "--:--")} às ${esc(agoraInfo.fim || "--:--")}` : "Disponível sob demanda"}</small>` +
          `<p>${esc(agoraInfo.descricao || "Informações de programação não disponíveis.")}</p>`;
      }
      set("[data-programa-seguir]", canal.aSeguir || "Programação não disponível");
    }

    /* ------------------------------------------------------ painel do player */
    function initPlayer() {
      const frame = document.querySelector("[data-player-frame] iframe");
      const botoes = [...document.querySelectorAll("[data-player-url]")];
      if (!frame || !botoes.length) return;

      if (!fontes.length) {
        botoes.forEach((btn) => btn.remove());
        frame.setAttribute("src", "about:blank");
        atualizarNotaFonte(null);
        return;
      }

      const fonteParaUrl = (fonte) => {
        if (fonte.tipo === "iframe") return fonte.url;
        const fallback = fonte.fallbackUrl
          ? `&fallback=${encodeURIComponent(fonte.fallbackUrl)}` +
            `&fallbackTipo=${encodeURIComponent(fonte.fallbackTipo || "ts")}`
          : "";
        return (
          `embed/player.html?src=${encodeURIComponent(fonte.url)}&tipo=${encodeURIComponent(fonte.tipo || "hls")}` +
          `&canal=${encodeURIComponent(canal.nome)}&label=${encodeURIComponent(fonte.label || "")}` +
          `&nome=${encodeURIComponent(fonte.nome || "")}&demo=${fonte.demo ? "1" : "0"}` +
          `&aoVivo=${aoVivo ? "1" : "0"}` +
          fallback
        );
      };

      botoes.forEach((btn, indice) => {
        const fonte = fontes[indice];
        if (!fonte) {
          btn.remove();
          return;
        }
        btn.dataset.playerUrl = fonteParaUrl(fonte);
        btn.querySelector("span").textContent = String(indice + 1);
        btn.setAttribute("aria-label", `${fonte.label} de ${canal.nome}`);
        btn.title = fonte.nome || fonte.label;

        btn.addEventListener("click", () => {
          const url = btn.dataset.playerUrl;
          if (!url || frame.getAttribute("src") === url) return;
          botoes.forEach((x) => x.classList.remove("active"));
          btn.classList.add("active");
          frame.setAttribute("src", url);
          atualizarNotaFonte(fonte);
          document.querySelector("[data-player-frame]")?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      });

      botoes[0].classList.add("active");
      frame.setAttribute("src", botoes[0].dataset.playerUrl);
      frame.setAttribute("title", `${canal.nome} ${aoVivo ? "ao vivo" : "sob demanda"}`);
      atualizarNotaFonte(fontes[0]);
    }

    /* Mostra qual conteúdo está tocando e a origem da playlist. */
    function atualizarNotaFonte(fonte) {
      const nota = document.querySelector("[data-source-note]");
      if (!nota) return;
      if (!fonte) {
        nota.classList.remove("is-demo");
        nota.textContent = "Nenhuma fonte de transmissão disponível para este canal.";
        return;
      }
      nota.classList.toggle("is-demo", !!fonte.demo);
      let origem = "";
      if (canal.origem && canal.origem.playlist) {
        const playlist = (window.CANAIS_EXTRA_PLAYLISTS || []).find(
          (p) => p.id === canal.origem.playlistId
        );
        const link = playlist && playlist.url
          ? `<span class="source-playlist-url">Link da playlist: <code>${esc(
              window.canaisMascararUrl ? window.canaisMascararUrl(playlist.url) : playlist.url
            )}</code></span>`
          : "";
        origem = ` Importado da playlist <strong>${esc(canal.origem.playlist)}</strong>.${link}`;
      }
      if (fonte.tipo === "iframe" && !fonte.demo) {
        nota.innerHTML =
          `<strong>Página incorporada:</strong> ${esc(fonte.nome || fonte.url)}. ` +
          `Se não aparecer, a página pode enviar <code>X-Frame-Options</code> ou ` +
          `<code>CSP frame-ancestors</code> bloqueando a incorporação.` +
          origem;
        return;
      }
      nota.innerHTML = fonte.demo
        ? `<strong>Fonte de teste.</strong> Esta opção reproduz <em>${esc(fonte.nome || "um vídeo de teste")}</em> —
           não é a transmissão de ${esc(canal.nome)}.`
        : `<strong>Tocando:</strong> ${esc(fonte.nome || fonte.label)}.${origem}`;
    }

    /* --------------------------------------------------------- tela ampla */
    function initTelaAmpla() {
      const botao = document.querySelector("[data-theater-toggle]");
      const layout = document.querySelector("[data-watch-layout]");
      if (!botao || !layout) return;

      botao.addEventListener("click", () => {
        const ativo = layout.classList.toggle("theater-mode");
        botao.classList.toggle("active", ativo);
        const rotulo = botao.querySelector("span");
        if (rotulo) rotulo.textContent = ativo ? "Tela normal" : "Tela ampla";
        document.querySelector("[data-player-frame]")?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }

    preencherCabecalho();
    initPlayer();
    initTelaAmpla();
  }

  if (!window.CANAIS_CATALOGO_PRONTO) {
    document.addEventListener("eftv:catalogo-pronto", iniciar, { once: true });
  } else {
    iniciar();
  }
})();
