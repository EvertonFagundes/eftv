/* ============================================================
   EFTV — Persistência local (espelha o SQLite/SharedPreferences)
   Favoritos, recentes, progresso, ajustes, sessão e device id.
   ============================================================ */

(() => {
  "use strict";

  const PREFIX = "eftv:";

  function ler(chave, padrao) {
    try {
      const bruto = localStorage.getItem(PREFIX + chave);
      if (bruto === null) return padrao;
      return JSON.parse(bruto);
    } catch (_) {
      return padrao;
    }
  }

  function gravar(chave, valor) {
    try {
      localStorage.setItem(PREFIX + chave, JSON.stringify(valor));
      return true;
    } catch (_) {
      return false;
    }
  }

  function remover(chave) {
    try { localStorage.removeItem(PREFIX + chave); } catch (_) {}
  }

  // Device id estável (equivalente ao hash do ANDROID_ID no Android)
  function deviceId() {
    let id = ler("device_id", null);
    if (!id) {
      const aleatorio =
        (crypto.randomUUID && crypto.randomUUID()) ||
        (Date.now().toString(36) + Math.random().toString(36).slice(2));
      id = window.EFTV_CONFIG.DEVICE_PREFIX + "-" + aleatorio;
      gravar("device_id", id);
    }
    return id;
  }

  const store = {
    ler,
    gravar,
    remover,
    deviceId,

    // ---------- Sessão ----------
    getSession() {
      return ler("session", null);
    },
    setSession(sessao) {
      gravar("session", sessao);
    },
    clearSession() {
      remover("session");
    },

    // ---------- Favoritos ----------
    getFavorites() {
      return new Set(ler("favorites", []));
    },
    setFavorites(set) {
      gravar("favorites", [...set]);
    },

    // ---------- Recentes ----------
    getRecents() {
      return ler("recents", []);
    },
    addRecent(item) {
      const lista = ler("recents", []).filter((i) => String(i.id) !== String(item.id));
      lista.unshift({ ...item, vistoEm: Date.now() });
      gravar("recents", lista.slice(0, 40));
    },

    // ---------- Progresso / continuar assistindo ----------
    getProgress() {
      return ler("progress", {});
    },
    saveProgress(id, dados) {
      const mapa = ler("progress", {});
      mapa[String(id)] = { ...(mapa[String(id)] || {}), ...dados, atualizadoEm: Date.now() };
      gravar("progress", mapa);
    },
    removeProgress(id) {
      const mapa = ler("progress", {});
      delete mapa[String(id)];
      gravar("progress", mapa);
    },
    getContinueWatching() {
      const mapa = ler("progress", {});
      return Object.entries(mapa)
        .map(([id, dados]) => ({ id, ...dados }))
        .filter((i) => i.progresso > 0 && i.progresso < 95)
        .sort((a, b) => (b.atualizadoEm || 0) - (a.atualizadoEm || 0));
    },

    // ---------- Ajustes ----------
    getSettings() {
      return {
        adulto: false,
        modoTV: false,
        economizarDados: false,
        autoplay: true,
        ...ler("settings", {}),
      };
    },
    saveSettings(parcial) {
      const atual = this.getSettings();
      gravar("settings", { ...atual, ...parcial });
    },

    // ---------- Cache do catálogo ----------
    getCatalogCache() {
      return ler("catalog", null);
    },
    setCatalogCache(dados) {
      gravar("catalog", { ...dados, salvoEm: Date.now() });
    },
  };

  window.EFTV_STORE = store;
})();