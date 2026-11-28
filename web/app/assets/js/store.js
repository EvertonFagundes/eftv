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

  // ------------------------------------------------------------------
  // IndexedDB — catálogo grande (dezenas de milhares de itens)
  // localStorage fica só para dados pequenos (sessão, favoritos etc.).
  // ------------------------------------------------------------------
  const DB_NAME = "eftv-web";
  const DB_VERSION = 1;
  const DB_STORE = "catalog";
  let dbPromise = null;

  function abrirDB() {
    if (dbPromise) return dbPromise;
    if (typeof indexedDB === "undefined") {
      dbPromise = Promise.resolve(null);
      return dbPromise;
    }
    dbPromise = new Promise((resolver) => {
      let req;
      try {
        req = indexedDB.open(DB_NAME, DB_VERSION);
      } catch (_) {
        resolver(null);
        return;
      }
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(DB_STORE)) db.createObjectStore(DB_STORE);
      };
      req.onsuccess = () => resolver(req.result);
      req.onerror = () => resolver(null);
      req.onblocked = () => resolver(null);
    });
    return dbPromise;
  }

  async function idbGet(chave) {
    const db = await abrirDB();
    if (!db) return null;
    return new Promise((resolver) => {
      try {
        const tx = db.transaction(DB_STORE, "readonly");
        const req = tx.objectStore(DB_STORE).get(chave);
        req.onsuccess = () => resolver(req.result ?? null);
        req.onerror = () => resolver(null);
      } catch (_) {
        resolver(null);
      }
    });
  }

  async function idbSet(chave, valor) {
    const db = await abrirDB();
    if (!db) return false;
    return new Promise((resolver) => {
      try {
        const tx = db.transaction(DB_STORE, "readwrite");
        tx.objectStore(DB_STORE).put(valor, chave);
        tx.oncomplete = () => resolver(true);
        tx.onerror = () => resolver(false);
        tx.onabort = () => resolver(false);
      } catch (_) {
        resolver(false);
      }
    });
  }

  async function idbDelete(chave) {
    const db = await abrirDB();
    if (!db) return;
    return new Promise((resolver) => {
      try {
        const tx = db.transaction(DB_STORE, "readwrite");
        tx.objectStore(DB_STORE).delete(chave);
        tx.oncomplete = () => resolver();
        tx.onerror = () => resolver();
        tx.onabort = () => resolver();
      } catch (_) {
        resolver();
      }
    });
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
        proxyStreams: true,
        overscan: 0,
        ...ler("settings", {}),
      };
    },
    saveSettings(parcial) {
      const atual = this.getSettings();
      gravar("settings", { ...atual, ...parcial });
    },

    // ---------- Cache do catálogo ----------
    // O catálogo real pode ter dezenas de milhares de itens; por isso vive no
    // IndexedDB. O localStorage continua como fallback para o modo demo e
    // navegadores sem IndexedDB.
    getCatalogCache() {
      return ler("catalog", null);
    },
    setCatalogCache(dados) {
      gravar("catalog", { ...dados, salvoEm: Date.now() });
    },
    async getCatalogCacheAsync() {
      const salvo = await idbGet("atual");
      if (salvo) return salvo;
      return ler("catalog", null);
    },
    async setCatalogCacheAsync(dados) {
      const registro = { ...dados, salvoEm: Date.now() };
      const ok = await idbSet("atual", registro);
      if (ok) {
        // Evita duas cópias grandes: o IndexedDB é a fonte.
        remover("catalog");
      } else {
        gravar("catalog", registro);
      }
      return ok;
    },
    async clearCatalogCacheAsync() {
      await idbDelete("atual");
      remover("catalog");
    },
  };

  window.EFTV_STORE = store;
})();