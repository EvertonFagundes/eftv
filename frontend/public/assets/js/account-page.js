// account-page.js - Área do assinante
import { api } from './api.js'
import { auth } from './auth.js'
import { account } from './account.js'
import { utils } from './utils.js'

// Verifica autenticação
if (!auth.requireAuth()) {
  // auth.requireAuth já redireciona se não logado
}

// Inicializa account
account.load()

// Tabs
document.querySelectorAll('.account-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.account-tab').forEach(t => t.classList.remove('is-active'))
    document.querySelectorAll('.account-panel').forEach(p => p.hidden = true)
    tab.classList.add('is-active')
    document.getElementById(`panel-${tab.dataset.tab}`).hidden = false
  })
})

// Logout
document.getElementById('logout-btn').addEventListener('click', () => auth.logout())

// Atualiza saudação
auth.subscribe(user => {
  const greeting = document.getElementById('user-greeting')
  if (greeting && user) {
    greeting.textContent = `Olá, ${utils.escapeHtml(user.full_name || user.email.split('@')[0])}`
  }
})

// Renderiza subscription card
account.subscribe(state => {
  renderSubscriptionCard()
  renderPayments()
  renderDevices()
})

function renderSubscriptionCard() {
  const card = document.getElementById('subscription-card')
  const actions = document.getElementById('subscription-actions')

  if (!account.subscription) {
    card.innerHTML = `
      <div class="empty-subscription">
        <svg viewBox="0 0 24 24" width="48" height="48"><path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22ZM12 20C7.58172 20 4 16.4183 4 12C4 7.58172 7.58172 4 12 4C16.4183 4 20 7.58172 20 12C20 16.4183 16.4183 20 12 20ZM12 6C10.3431 6 9 7.34315 9 9C9 10.6569 10.3431 12 12 12C13.6569 12 15 10.6569 15 9C15 7.34315 13.6569 6 12 6Z"/></svg>
        <h3>Nenhuma assinatura ativa</h3>
        <p>Você não possui assinatura no momento.</p>
        <a href="plans.html" class="btn btn-primary">Ver planos</a>
      </div>
    `
    actions.hidden = true
    return
  }

  const sub = account.subscription
  const isActive = sub.is_active
  const isTrial = sub.is_trial
  const isPastDue = sub.status === 'past_due'
  const isCancelled = sub.cancel_at_period_end

  card.innerHTML = `
    <div class="subscription-header">
      <div class="subscription-main">
        <div class="subscription-plan">${utils.escapeHtml(sub.plan_name)}</div>
        <div class="subscription-status ${account.getStatusClass(sub.status)}">${account.getStatusLabel(sub.status)}</div>
      </div>
      <div class="subscription-period">
        <div class="period-item">
          <span class="period-label">Início</span>
          <span class="period-value">${utils.formatDate(sub.current_period_start)}</span>
        </div>
        <div class="period-item">
          <span class="period-label">${isTrial ? 'Fim do teste' : 'Renovação'}</span>
          <span class="period-value">${utils.formatDate(sub.current_period_end)}</span>
        </div>
        ${sub.days_remaining > 0 ? `
        <div class="period-item highlight">
          <span class="period-label">Dias restantes</span>
          <span class="period-value">${sub.days_remaining} dia${sub.days_remaining > 1 ? 's' : ''}</span>
        </div>
        ` : ''}
      </div>
    </div>
    <div class="subscription-details">
      <div class="detail-row">
        <span>Método de pagamento</span>
        <span>Mercado Pago (PIX/Cartão/Boleto)</span>
      </div>
      <div class="detail-row">
        <span>Renovação automática</span>
        <span>${sub.auto_renew ? 'Ativada' : 'Desativada'}</span>
      </div>
    </div>
  `

  // Ações
  actions.hidden = false
  actions.innerHTML = `
    ${isActive && !isCancelled ? `
      <button class="btn btn-danger" id="cancel-sub-btn">Cancelar assinatura</button>
    ` : ''}
    ${isCancelled ? `
      <button class="btn btn-primary" id="reactivate-sub-btn">Reativar assinatura</button>
    ` : ''}
    ${isPastDue ? `
      <a href="plans.html" class="btn btn-primary">Regularizar pagamento</a>
    ` : ''}
    <a href="plans.html" class="btn btn-outline">Gerenciar plano</a>
  `

  // Event listeners
  const cancelBtn = document.getElementById('cancel-sub-btn')
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      if (confirm('Tem certeza? Seu acesso continuará até o fim do período pago.')) {
        await account.cancelSubscription()
      }
    })
  }

  const reactivateBtn = document.getElementById('reactivate-sub-btn')
  if (reactivateBtn) {
    reactivateBtn.addEventListener('click', async () => {
      // TODO: implementar reativação via API
      alert('Funcionalidade em desenvolvimento')
    })
  }
}

function renderPayments() {
  const list = document.getElementById('payments-list')
  if (!list) return

  if (!account.paymentHistory.length) {
    list.innerHTML = '<div class="empty-state">Nenhum pagamento registrado</div>'
    return
  }

  list.innerHTML = account.paymentHistory.map(p => `
    <article class="payment-item">
      <div class="payment-info">
        <div class="payment-title">${utils.escapeHtml(p.payment_method || 'Pagamento')}</div>
        <div class="payment-meta">${utils.formatDateTime(p.created_at)} • ${utils.formatPrice(p.amount_cents, p.currency)}</div>
      </div>
      <span class="payment-status status-${p.status}">${p.status}</span>
    </article>
  `).join('')
}

function renderDevices() {
  const list = document.getElementById('devices-list')
  if (!list) return

  // TODO: buscar sessões de playback via API
  list.innerHTML = '<div class="empty-state">Nenhum dispositivo ativo no momento</div>'
}

// Profile form
const profileForm = document.getElementById('profile-form')
if (profileForm) {
  auth.subscribe(user => {
    if (user) {
      document.getElementById('profile_name').value = user.full_name || ''
      document.getElementById('profile_email').value = user.email
      document.getElementById('profile_phone').value = user.phone || ''
    }
  })

  profileForm.addEventListener('submit', async e => {
    e.preventDefault()
    const formData = new FormData(profileForm)
    try {
      await auth.updateMe({
        full_name: formData.get('full_name'),
        phone: formData.get('phone'),
      })
      showToast('Perfil atualizado com sucesso')
    } catch (error) {
      showToast(error.message, 'error')
    }
  })
}

// Password form
const passwordForm = document.getElementById('password-form')
const newPasswordInput = document.getElementById('new_password')
const strengthEl2 = document.getElementById('password-strength-2')

if (passwordForm) {
  newPasswordInput.addEventListener('input', () => {
    const { score, label, color } = checkPasswordStrength(newPasswordInput.value)
    strengthEl2.innerHTML = `<div class="strength-bar"><div class="strength-fill" style="width: ${(score/5)*100}%; background: ${color}"></div></div><span style="color:${color}">${label}</span>`
  })

  passwordForm.addEventListener('submit', async e => {
    e.preventDefault()
    const formData = new FormData(passwordForm)
    if (formData.get('new_password') !== formData.get('confirm_new_password')) {
      showToast('Senhas não coincidem', 'error')
      return
    }
    try {
      await auth.updateMe({ password: formData.get('new_password') })
      showToast('Senha alterada com sucesso')
      passwordForm.reset()
      strengthEl2.innerHTML = ''
    } catch (error) {
      showToast(error.message, 'error')
    }
  })
}

function checkPasswordStrength(password) {
  let score = 0
  if (password.length >= 8) score++
  if (/[A-Z]/.test(password)) score++
  if (/[a-z]/.test(password)) score++
  if (/[0-9]/.test(password)) score++
  if (/[^A-Za-z0-9]/.test(password)) score++

  const labels = ['Muito fraca', 'Fraca', 'Média', 'Forte', 'Muito forte']
  const colors = ['#e74c3c', '#e67e22', '#f39c12', '#27ae60', '#2ecc71']
  return { score, label: labels[score], color: colors[score] }
}

function showToast(message, type = 'success') {
  const toast = document.createElement('div')
  toast.className = `toast toast-${type}`
  toast.textContent = message
  document.body.appendChild(toast)
  setTimeout(() => toast.classList.add('show'), 10)
  setTimeout(() => {
    toast.classList.remove('show')
    setTimeout(() => toast.remove(), 300)
  }, 3000)
}