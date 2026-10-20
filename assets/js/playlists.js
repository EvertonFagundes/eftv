/* EFTV - importação de playlists .m3u/.m3u8.
   No servidor local fala com a API do server.py. No GitHub Pages usa o
   armazenamento local (IndexedDB) do modo estático. Depois de cada mudança
   atualiza a lista, o catálogo e a grade sem recarregar a página. */

(function () {
  const escapeHtml = window.canaisEscape || ((v) => String(v));
  const form = document.querySelector("[data-playlist-form]");
  if (!form) return;

  const inputUrl = document.querySelector("[data-playlist-url]");
  const botaoAdd = document.querySelector("[data-playlist-add]");
  const inputFile = document.querySelector("[data-playlist-file]");
  const nomeArquivo = document.querySelector("[data-playlist-file-name]");
  const status = document.querySelector("[data-playlist-status]");
  const lista = document.querySelector("[data-playlist-list]");
  const vazio = document.querySelector("[data-playlist-empty]");
  const botaoLimpar = document.querySelector("[data-playlist-clear]");
  const estatico = !!window.CANAIS_STATIC && !!window.EFTVStatic;

  let playlists = Array.isArray(window.CANAIS_EXTRA_PLAYLISTS)
    ? window.CANAIS_EXTRA_PLAYLISTS.slice()
    : [];
  let ocupado = false;

  /* ------------------------------------------------------------- feedback */
  function mostrarStatus(mensagem, tipo) {
    if (!status) return;
    status.textContent = mensagem;
    status.classList.remove("is-ok", "is-error");
    if (tipo) status.classList.add(tipo === "ok" ? "is-ok" : "is-error");
    status.hidden = !mensagem;
  }

  function ocupar(valor) {
    ocupado = valor;
    if (botaoAdd) {
      botaoAdd.disabled = valor;
      botaoAdd.textContent = valor ? "Aguarde..." : "Adicionar link";
    }
    if (botaoLimpar) botaoLimpar.disabled = valor;
    if (lista) {
      lista.querySelectorAll("button").forEach((btn) => {
        btn.disabled = valor;
      });
    }
  }

  async function lerResposta(resp) {
    let dados = null;
    try {
      dados = await resp.json();
    } catch (_) {
      throw new Error("O servidor local não respondeu como esperado. Inicie com python3 server.py.");
    }
    if (!resp.ok || !dados || dados.ok === false) {
      throw new Error((dados && dados.error) || "Não foi possível concluir a operação.");
    }
    return dados;
  }

  async function pedir(url, opcoes) {
    let resp;
    try {
      resp = await fetch(url, { cache: "no-store", ...opcoes });
    } catch (_) {
      throw new Error(
        "Não foi possível falar com o servidor local. Verifique se o server.py está rodando na porta 8124."
      );
    }
    return lerResposta(resp);
  }

  /* --------------------------------------------------------------- lista */
  async function copiarTexto(texto) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(texto);
        return;
      }
    } catch (_) {
      // Permissão negada: tenta o método antigo abaixo.
    }
    const area = document.createElement("textarea");
    area.value = texto;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    if (!ok) throw new Error("Não foi possível copiar.");
  }

  function renderLista() {
    if (!lista) return;
    lista.innerHTML = playlists
      .map((p) => {
        const nome = escapeHtml(p.name || "Playlist");
        const id = escapeHtml(p.id || "");
        const qtd = Number(p.count) || 0;
        const qtdTexto = qtd.toLocaleString("pt-BR");
        const url = (p.url || "").trim();
        const urlExibida = window.canaisMascararUrl ? window.canaisMascararUrl(url) : url;
        const link = url
          ? `<div class="playlist-source">
               <span class="playlist-source-label">Link:</span>
               <code class="playlist-link">${escapeHtml(urlExibida)}</code>
               <button class="playlist-btn mini" type="button" data-copy="${id}">Copiar link</button>
             </div>`
          : `<div class="playlist-source">
               <span class="playlist-source-label">Origem:</span>
               <span>arquivo enviado</span>
             </div>`;
        const atualizar = p.uploaded
          ? ""
          : `<button class="playlist-btn mini" type="button" data-refresh="${id}">Atualizar</button>`;
        return `
        <div class="playlist-item">
          <div class="playlist-item-main">
            <strong>${nome}</strong>
            <span>${qtdTexto} ${qtd === 1 ? "canal" : "canais"}</span>
            ${link}
          </div>
          <div class="playlist-item-actions">
            ${atualizar}
            <button class="playlist-btn mini danger" type="button" data-remove="${id}">Remover</button>
          </div>
        </div>`;
      })
      .join("");

    if (vazio) vazio.hidden = playlists.length !== 0;
    if (botaoLimpar) botaoLimpar.hidden = playlists.length === 0;
  }

  async function carregarLista() {
    if (estatico) {
      const itens = await window.EFTVStatic.listar();
      playlists = itens.map(window.EFTVStatic.resumir);
    } else {
      playlists = Array.isArray(window.CANAIS_EXTRA_PLAYLISTS)
        ? window.CANAIS_EXTRA_PLAYLISTS.slice()
        : [];
    }
    renderLista();
  }

  /* ------------------------------------------------------ catálogo / grade */
  async function recarregarCatalogo() {
    if (estatico) {
      await window.EFTVStatic.reconstruir();
      await carregarLista();
      if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
      return;
    }

    const dados = await pedir("/api/catalogo.json");
    if (typeof window.CanaisAplicarCatalogo !== "function") {
      throw new Error("Catálogo do site não carregou. Recarregue a página.");
    }
    window.CanaisAplicarCatalogo(dados);
    playlists = Array.isArray(dados.playlists) ? dados.playlists : [];
    if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
    if (typeof window.CanaisAplicarFiltro === "function") window.CanaisAplicarFiltro();
    renderLista();
  }

  /* ------------------------------------------------------------- ações */
  async function adicionarUrl(url) {
    ocupar(true);
    mostrarStatus("Buscando playlist e lendo os canais...", null);
    try {
      const dados = estatico
        ? await window.EFTVStatic.adicionarUrl(url)
        : await pedir("/api/playlists", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
          });
      if (estatico) {
        await carregarLista();
        if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
      } else {
        await recarregarCatalogo();
      }
      if (inputUrl) inputUrl.value = "";
      mostrarStatus(dados.message || "Playlist adicionada.", "ok");
    } catch (erro) {
      mostrarStatus(erro.message, "error");
    } finally {
      ocupar(false);
    }
  }

  async function enviarArquivo(file) {
    ocupar(true);
    mostrarStatus(`Lendo "${file.name}"...`, null);
    try {
      let dados;
      if (estatico) {
        dados = await window.EFTVStatic.adicionarArquivo(file);
        await carregarLista();
        if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
      } else {
        const texto = await file.text();
        dados = await pedir(
          "/api/playlists/upload?name=" + encodeURIComponent(file.name.replace(/\.(m3u8?)$/i, "")),
          {
            method: "POST",
            headers: { "Content-Type": "text/plain; charset=utf-8" },
            body: texto,
          }
        );
        await recarregarCatalogo();
      }
      if (inputFile) inputFile.value = "";
      if (nomeArquivo) nomeArquivo.textContent = "Nenhum arquivo selecionado";
      mostrarStatus(dados.message || "Playlist importada.", "ok");
    } catch (erro) {
      mostrarStatus(erro.message, "error");
    } finally {
      ocupar(false);
    }
  }

  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    if (ocupado) return;
    const url = (inputUrl && inputUrl.value ? inputUrl.value : "").trim();
    if (!url) {
      mostrarStatus("Cole o link de uma playlist .m3u ou .m3u8.", "error");
      inputUrl && inputUrl.focus();
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      mostrarStatus("O link precisa começar com http:// ou https://.", "error");
      return;
    }
    adicionarUrl(url);
  });

  if (inputFile) {
    inputFile.addEventListener("change", () => {
      const file = inputFile.files && inputFile.files[0];
      if (!file) return;
      if (nomeArquivo) nomeArquivo.textContent = file.name;
      if (!/\.m3u8?$/i.test(file.name)) {
        mostrarStatus("Escolha um arquivo com extensão .m3u ou .m3u8.", "error");
        inputFile.value = "";
        if (nomeArquivo) nomeArquivo.textContent = "Nenhum arquivo selecionado";
        return;
      }
      enviarArquivo(file);
    });
  }

  if (lista) {
    lista.addEventListener("click", async (evento) => {
      if (ocupado) return;

      const copiar = evento.target.closest("[data-copy]");
      if (copiar) {
        const id = copiar.getAttribute("data-copy");
        const item = playlists.find((p) => p.id === id);
        if (!item || !item.url) return;
        try {
          await copiarTexto(item.url);
          mostrarStatus("Link copiado para a área de transferência.", "ok");
        } catch (_) {
          mostrarStatus("Não foi possível copiar o link.", "error");
        }
        return;
      }

      const remover = evento.target.closest("[data-remove]");
      if (remover) {
        const id = remover.getAttribute("data-remove");
        const item = playlists.find((p) => p.id === id);
        const nome = item ? item.name : "esta playlist";
        if (!confirm(`Remover "${nome}" e todos os canais importados por ela?`)) return;
        ocupar(true);
        mostrarStatus("Removendo playlist...", null);
        try {
          if (estatico) {
            await window.EFTVStatic.remover(id);
            await carregarLista();
            if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
          } else {
            await pedir("/api/playlists?id=" + encodeURIComponent(id), { method: "DELETE" });
            await recarregarCatalogo();
          }
          mostrarStatus("Playlist removida.", "ok");
        } catch (erro) {
          mostrarStatus(erro.message, "error");
        } finally {
          ocupar(false);
        }
        return;
      }

      const atualizar = evento.target.closest("[data-refresh]");
      if (atualizar) {
        const id = atualizar.getAttribute("data-refresh");
        ocupar(true);
        mostrarStatus("Buscando a versão mais recente da playlist...", null);
        try {
          let dados;
          if (estatico) {
            dados = await window.EFTVStatic.atualizar(id);
            await carregarLista();
            if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
          } else {
            dados = await pedir("/api/playlists/refresh", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id }),
            });
            await recarregarCatalogo();
          }
          mostrarStatus(dados.message || "Playlist atualizada.", "ok");
        } catch (erro) {
          mostrarStatus(erro.message, "error");
        } finally {
          ocupar(false);
        }
      }
    });
  }

  if (botaoLimpar) {
    botaoLimpar.addEventListener("click", async () => {
      if (ocupado || !playlists.length) return;
      if (!confirm("Remover todas as playlists importadas?")) return;
      ocupar(true);
      mostrarStatus("Removendo playlists...", null);
      try {
        if (estatico) {
          await window.EFTVStatic.limpar();
          await carregarLista();
          if (typeof window.CanaisRenderTudo === "function") window.CanaisRenderTudo();
        } else {
          await pedir("/api/playlists/clear", { method: "POST" });
          await recarregarCatalogo();
        }
        mostrarStatus("Todas as playlists foram removidas.", "ok");
      } catch (erro) {
        mostrarStatus(erro.message, "error");
      } finally {
        ocupar(false);
      }
    });
  }

  document.addEventListener("eftv:catalogo-pronto", () => {
    carregarLista().catch(() => {});
  });

  carregarLista().catch(() => renderLista());
  if (window.CANAIS_CATALOGO_PRONTO) {
    carregarLista().catch(() => {});
  }
})();
