/* EFTV - instalação como aplicativo (PWA).
   Registra o service worker e usa o prompt nativo de instalação quando o
   navegador oferece. Em iPhones/iPads e navegadores sem prompt, mostra as
   instruções manuais. */

(function () {
  const botoes = [...document.querySelectorAll("[data-install-app]")];
  const dialogo = document.querySelector("[data-install-dialog]");
  let promptDiferido = null;

  function standalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.navigator.standalone === true
    );
  }

  function mostrarBotoes() {
    if (standalone()) return;
    botoes.forEach((btn) => {
      btn.hidden = false;
    });
  }

  function esconderBotoes() {
    botoes.forEach((btn) => {
      btn.hidden = true;
    });
  }

  function abrirInstrucoes() {
    if (!dialogo) return;
    if (typeof dialogo.showModal === "function") {
      if (!dialogo.open) dialogo.showModal();
    } else {
      window.alert(
        "Para instalar: no Chrome/Edge use o menu do navegador e escolha “Instalar app”. No iPhone/iPad, toque em Compartilhar e depois em “Adicionar à Tela de Início”."
      );
    }
  }

  window.addEventListener("beforeinstallprompt", (evento) => {
    evento.preventDefault();
    promptDiferido = evento;
    mostrarBotoes();
  });

  window.addEventListener("appinstalled", () => {
    promptDiferido = null;
    esconderBotoes();
  });

  botoes.forEach((botao) => {
    botao.addEventListener("click", async () => {
      if (promptDiferido) {
        const prompt = promptDiferido;
        promptDiferido = null;
        prompt.prompt();
        try {
          const escolha = await prompt.userChoice;
          if (escolha && escolha.outcome === "accepted") esconderBotoes();
        } catch (_) {
          // Se o prompt falhar, as instruções manuais continuam disponíveis.
        }
        return;
      }
      abrirInstrucoes();
    });
  });

  if (dialogo) {
    dialogo.querySelectorAll("[data-install-close]").forEach((botao) => {
      botao.addEventListener("click", () => {
        if (typeof dialogo.close === "function") dialogo.close();
        else dialogo.removeAttribute("open");
      });
    });
    dialogo.addEventListener("click", (evento) => {
      if (evento.target === dialogo && typeof dialogo.close === "function") dialogo.close();
    });
  }

  // O botão fica disponível mesmo quando o navegador não dispara o prompt
  // (por exemplo, Safari/iOS): nesse caso ele abre as instruções manuais.
  if (!standalone()) {
    setTimeout(mostrarBotoes, 1200);
  }

  if (
    "serviceWorker" in navigator &&
    (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")
  ) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch((erro) => {
        console.warn("EFTV: não foi possível registrar o service worker.", erro);
      });
    });
  }
})();
