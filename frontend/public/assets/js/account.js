// account.js - Área do assinante (minha conta, assinatura, pagamentos)
import { api } from './api.js'
import { auth } from './auth.js'

export const account = {
  subscription: null,
  paymentHistory: [],
  _listeners: new Set(),

  subscribe(listener) {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  },

  _notify() {
    this._listeners.forEach(fn => fn(this))
  },

  async load() {
    if (!auth.isAuthenticated) return

    const subscriptions = await api.getMySubscriptions()
    // Pega a mais recente ativa/trial
    this.subscription = subscriptions.find(s => s.is_active || s.is_trial) || subscriptions[0] || null

    if (this.subscription) {
      this.paymentHistory = await api.getSubscription(this.subscription.id).catch(() => [])
    }
    this._notify()
  },

  async createCheckout(planId, paymentMethod = 'pix') {
    const data = await api.createCheckout({ plan_id: planId, payment_method: paymentMethod })
    return data.init_point // URL para redirecionar
  },

  async cancelSubscription() {
    if (!this.subscription) return
    await api.cancelSubscription(this.subscription.id)
    await this.load()
  },

  formatPrice(cents, currency = 'BRL') {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format(cents / 100)
  },

  formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  },

  getStatusLabel(status) {
    const labels = {
      active: 'Ativa',
      trial: 'Período de teste',
      past_due: 'Pagamento pendente',
      cancelled: 'Cancelada',
      expired: 'Expirada',
      pending: 'Aguardando pagamento',
    }
    return labels[status] || status
  },

  getStatusClass(status) {
    const classes = {
      active: 'status-active',
      trial: 'status-trial',
      past_due: 'status-past-due',
      cancelled: 'status-cancelled',
      expired: 'status-expired',
      pending: 'status-pending',
    }
    return classes[status] || ''
  },
}

export default account