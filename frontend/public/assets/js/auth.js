// auth.js - Gerenciamento de autenticação no frontend
import { api } from './api.js'

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
    // Tenta restaurar sessão do localStorage
    const saved = localStorage.getItem(AUTH_KEY)
    if (saved) {
      try {
        const { accessToken } = JSON.parse(saved)
        if (accessToken) {
          api.setTokens(accessToken, null)
          const user = await api.getMe().catch(() => null)
          if (user) {
            this._user = user
            this._notify()
            return true
          }
        }
      } catch {}
    }
    return false
  },

  async login(email, password) {
    const data = await api.login(email, password)
    api.setTokens(data.access_token, data.refresh_token)
    this._saveTokens(data.access_token, data.refresh_token)
    this._user = await api.getMe()
    this._saveUser(this._user)
    this._notify()
    return this._user
  },

  async register(data) {
    const result = await api.register(data)
    api.setTokens(result.access_token, result.refresh_token)
    this._saveTokens(result.access_token, result.refresh_token)
    this._user = await api.getMe()
    this._saveUser(this._user)
    this._notify()
    return this._user
  },

  async logout() {
    await api.logout()
    this.clear()
    window.location.href = '/login.html'
  },

  clear() {
    this._user = null
    api.clearTokens()
    localStorage.removeItem(AUTH_KEY)
    localStorage.removeItem(USER_KEY)
    this._notify()
  },

  _saveTokens(access, refresh) {
    localStorage.setItem(AUTH_KEY, JSON.stringify({ accessToken: access, refreshToken: refresh }))
  },

  _saveUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  // Helpers para UI
  requireAuth() {
    if (!this.isAuthenticated) {
      window.location.href = '/login.html?redirect=' + encodeURIComponent(window.location.pathname)
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