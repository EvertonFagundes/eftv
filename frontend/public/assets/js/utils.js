// utils.js - Helpers diversos (escape, normalize, formatação)
export const utils = {
  // Escape HTML para prevenir XSS
  escapeHtml(text) {
    if (!text) return ''
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  },

  // Normaliza string para busca (remove acentos, lowerCase)
  normalize(text) {
    if (!text) return ''
    return text
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim()
  },

  // Formata preço em centavos para moeda
  formatPrice(cents, currency = 'BRL') {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format(cents / 100)
  },

  // Formata data
  formatDate(dateString, options = {}) {
    const defaultOptions = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      ...options,
    }
    return new Date(dateString).toLocaleDateString('pt-BR', defaultOptions)
  },

  // Formata data e hora
  formatDateTime(dateString) {
    return new Date(dateString).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  },

  // Tempo relativo (ex: "há 5 min", "ontem", "3 dias atrás")
  timeAgo(dateString) {
    const now = new Date()
    const date = new Date(dateString)
    const diffMs = now - date
    const diffSecs = Math.floor(diffMs / 1000)
    const diffMins = Math.floor(diffSecs / 60)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffSecs < 60) return 'agora mesmo'
    if (diffMins < 60) return `há ${diffMins} min`
    if (diffHours < 24) return `há ${diffHours}h`
    if (diffDays < 7) return `há ${diffDays} dia${diffDays > 1 ? 's' : ''}`
    return this.formatDate(dateString)
  },

  // Gera slug a partir de string
  slugify(text) {
    return this.normalize(text)
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
  },

  // Trunca texto com ellipsis
  truncate(text, maxLength = 100) {
    if (!text || text.length <= maxLength) return text
    return text.slice(0, maxLength).trim() + '…'
  },

  // Debounce
  debounce(fn, delay = 300) {
    let timeoutId
    return (...args) => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => fn(...args), delay)
    }
  },

  // Throttle
  throttle(fn, limit = 300) {
    let inThrottle
    return (...args) => {
      if (!inThrottle) {
        fn(...args)
        inThrottle = true
        setTimeout(() => (inThrottle = false), limit)
      }
    }
  },

  // Query string helpers
  getQueryParam(name) {
    return new URLSearchParams(window.location.search).get(name)
  },

  setQueryParam(name, value) {
    const params = new URLSearchParams(window.location.search)
    if (value) params.set(name, value)
    else params.delete(name)
    window.history.replaceState({}, '', `${window.location.pathname}?${params}`)
  },

  // Copiar para clipboard
  async copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // Fallback
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      return true
    }
  },

  // Verifica se é dispositivo móvel
  isMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
  },

  // Formata número com separador de milhares
  formatNumber(num) {
    return new Intl.NumberFormat('pt-BR').format(num)
  },

  // Gera ID único simples
  generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2)
  },
}

export default utils