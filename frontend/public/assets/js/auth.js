// auth.js - Gerenciamento de autenticação no frontend
import { api } from './api.js'

// Chaves antigas: guardavam o refresh token no localStorage. Mantidas aqui
// apenas para limpar instalações existentes.
const AUTH_KEY = 'eftv_auth'
const USER_KEY = 'eftv_user'

export const auth = {
  // Estado reativo simples
  _user: null,
  _listeners: new Set(),

  get user() {
    return this._user
  },

  get isAuthenticated() {
    return !!this._user
  },

  subscribe(listener) {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  },

  _notify() {
    this._listeners.forEach(fn => fn(this._user))
  },

  async init() {
    // O refresh token fica em cookie HttpOnly (inacessível ao JavaScript).
    // O access token curto vive só na memória desta página: recarregar a
    // página pede um novo access token ao backend usando o cookie.
    this._limparArmazenamentoAntigo()

    const refreshed = await api.refreshAccessToken()
    if (!refreshed) return false

    const user = await api.getMe().catch(() => null)
    if (!user) {
      this.clear()
      return false
    }
    this._user = user
    this._notify()
    return true
  },

  async login(email, password) {
    const data = await api.login(email, password)
    api.setTokens(data.access_token, null)
    this._limparArmazenamentoAntigo()
    this._user = await api.getMe()
    this._notify()
    return this._user
  },

  async register(data) {
    const result = await api.register(data)
    api.setTokens(result.access_token, null)
    this._limparArmazenamentoAntigo()
    this._user = await api.getMe()
    this._notify()
    return this._user
  },

  async logout() {
    try {
      await api.logout()
    } catch {
      // Sem rede ou sessão já expirada: o importante é limpar o estado local.
    }
    this.clear()
    window.location.href = '/login.html'
  },

  clear() {
    this._user = null
    api.clearTokens()
    this._limparArmazenamentoAntigo()
    this._notify()
  },

  _limparArmazenamentoAntigo() {
    try {
      localStorage.removeItem(AUTH_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {
      // Modo privado / armazenamento bloqueado: não há o que limpar.
    }
  },

  // Helpers para UI
  requireAuth() {
    if (!this.isAuthenticated) {
      window.location.href = '/login.html?redirect=' +
        encodeURIComponent(window.location.pathname + window.location.search)
      return false
    }
    return true
  },

  redirectIfAuthenticated(target = '/account.html') {
    if (this.isAuthenticated) {
      window.location.href = target
      return true
    }
    return false
  },
}

// Escuta evento de logout forçado (ex: token expirado)
window.addEventListener('auth:logout', () => auth.clear())

export default auth
