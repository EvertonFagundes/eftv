// api.js - Cliente API com autenticação
class ApiClient {
  constructor(baseUrl = '/api') {
    this.baseUrl = baseUrl
    this.accessToken = null
    this.refreshToken = null
    this.refreshing = false
    this.refreshPromise = null
  }

  setTokens(access, refresh) {
    this.accessToken = access
    this.refreshToken = refresh
  }

  clearTokens() {
    this.accessToken = null
    this.refreshToken = null
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include', // Para cookies HttpOnly
    })

    if (response.status === 401 && !options._retry) {
      // Tenta renovar token
      const refreshed = await this.refreshAccessToken()
      if (refreshed) {
        // Repete a requisição original
        return this.request(endpoint, { ...options, _retry: true })
      }
      // Se falhou, limpa tokens e redireciona para login
      this.clearTokens()
      window.dispatchEvent(new CustomEvent('auth:logout'))
      throw new Error('Sessão expirada')
    }

    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(data.detail || `Erro ${response.status}`)
    }

    return data
  }

  async refreshAccessToken() {
    if (this.refreshing) {
      return this.refreshPromise
    }

    this.refreshing = true
    this.refreshPromise = (async () => {
      try {
        const response = await fetch(`${this.baseUrl}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        })
        if (response.ok) {
          const data = await response.json()
          this.accessToken = data.access_token
          return true
        }
        return false
      } catch {
        return false
      } finally {
        this.refreshing = false
        this.refreshPromise = null
      }
    })()

    return this.refreshPromise
  }

  // Auth
  async register(data) {
    return this.request('/auth/register', { method: 'POST', body: JSON.stringify(data) })
  }

  async login(email, password) {
    return this.request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
  }

  async logout() {
    await this.request('/auth/logout', { method: 'POST' })
    this.clearTokens()
  }

  async getMe() {
    return this.request('/auth/me')
  }

  async updateMe(data) {
    return this.request('/auth/me', { method: 'PATCH', body: JSON.stringify(data) })
  }

  // Plans
  async getPlans(params = {}) {
    const query = new URLSearchParams(params).toString()
    return this.request(`/plans?${query}`)
  }

  async getPlan(id) {
    return this.request(`/plans/${id}`)
  }

  // Channels
  async getChannels(params = {}) {
    const query = new URLSearchParams(params).toString()
    return this.request(`/channels?${query}`)
  }

  async getChannel(slug) {
    return this.request(`/channels/${slug}`)
  }

  async playChannel(slug) {
    return this.request(`/channels/${slug}/play`, { method: 'GET' })
  }

  // Categories
  async getCategories() {
    return this.request('/categories')
  }

  // Subscriptions
  async getMySubscriptions() {
    return this.request('/subscriptions')
  }

  async getSubscription(id) {
    return this.request(`/subscriptions/${id}`)
  }

  async createCheckout(data) {
    return this.request('/subscriptions/checkout', { method: 'POST', body: JSON.stringify(data) })
  }

  async cancelSubscription(id) {
    return this.request(`/subscriptions/${id}/cancel`, { method: 'POST' })
  }
}

export const api = new ApiClient()