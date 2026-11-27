/*======================================================================
  EFTV — PWA: instalação como atalho
  - Mostra botão "Instalar app" quando o navegador oferece o prompt nativo.
  - Em iOS/Safari e navegadores sem prompt, mostra instruções manuais.
  ======================================================================*/

(function () {
  "use strict";

  const botoes = [...document.querySelectorAll("[data-install-app]")];
  const dialogo = document.getElementById("install-dialog");
  let promptDiferido = null;

  function estaInstalado() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.navigator.standalone === true
    );
  }

  function mostrarBotoes() {
    if (estaInstalado()) return;
    botoes.forEach((btn) => { btn.hidden = false; });
  }

  function esconderBotoes() {
    botoes.forEach((btn) => { btn.hidden = true; });
  }

  function abrirDialogo() {
    if (!dialogo) return;
    if (typeof dialogo.showModal === "function") {
      dialogo.showModal();
    } else {
      dialogo.hidden = false;
    }
  }

  function fecharDialogo() {
    if (!dialogo) return;
    if (typeof dialogo.close === "function") {
      dialogo.close();
    } else {
      dialogo.hidden = true;
    }
  }

  window.addEventListener("beforeinstallprompt", (evento) => {
    evento.preventDefault(); // não mostra o prompt nativo automaticamente
    promptDiferido = evento;
    mostrarBotoes();
  });

  window.addEventListener("appinstalled", () => {
    promptDiferido = null;
    esconderBotoes();
    fecharDialogo();
  });

  botoes.forEach((botao) => {
    botao.addEventListener("click", async () => {
      if (promptDiferido) {
        const prompt = promptDiferido;
        promptDiferido = null;
        try {
          prompt.prompt();
          const escolha = await prompt.userChoice;
          if (escolha && escolha.outcome === "accepted") {
            esconderBotoes();
            fecharDialogo();
          }
        } catch (_) {
          abrirDialogo();
        }
        return;
      }
      abrirDialogo();
    });
  });

  // Fecha dialogo ao clicar fora ou no X
  if (dialogo) {
    dialogo.querySelectorAll("[data-install-close]").forEach((botao) => {
      botao.addEventListener("click", fecharDialogo);
    });
    dialogo.addEventListener("click", (evento) => {
      if (evento.target === dialogo && typeof dialogo.close === "function") {
        dialogo.close();
      }
    });
  }

  // Se o navegador não dispara o prompt (iOS, Safari etc.), ainda mostra o botão
  // depois de um curto atraso para levar às instruções manuais.
  if (!estaInstalado()) {
    setTimeout(mostrarBotoes, 1000);
  }

  // Registra o service worker (só em https, localhost ou 127.0.0.1)
  if (
    "serviceWorker" in navigator &&
    (location.protocol === "https:" ||
     location.hostname === "localhost" ||
     location.hostname === "127.0.0.1")
  ) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch((erro) => {
        console.warn("EFTV: não foi possível registrar o service worker.", erro);
      });
    });
  }
})();