// auth-page.js - Login e Register
import { api } from './api.js'
import { auth } from './auth.js'
import { utils } from './utils.js'

// Verifica se já logado e redireciona
auth.init().then(loggedIn => {
  if (loggedIn) {
    const redirect = utils.getQueryParam('redirect') || 'account.html'
    window.location.href = redirect
  }
})

// Login form
const loginForm = document.getElementById('login-form')
if (loginForm) {
  loginForm.addEventListener('submit', async e => {
    e.preventDefault()
    const formData = new FormData(loginForm)
    const submitBtn = loginForm.querySelector('button[type="submit"]')
    const originalText = submitBtn.textContent

    submitBtn.disabled = true
    submitBtn.textContent = 'Entrando...'

    try {
      await auth.login(formData.get('email'), formData.get('password'))
      const redirect = utils.getQueryParam('redirect') || 'account.html'
      window.location.href = redirect
    } catch (error) {
      showError(loginForm, error.message)
    } finally {
      submitBtn.disabled = false
      submitBtn.textContent = originalText
    }
  })
}

// Register form
const registerForm = document.getElementById('register-form')
if (registerForm) {
  const planOptions = document.getElementById('plan-options')
  const selectedPlanInput = document.getElementById('selected_plan')
  const passwordInput = document.getElementById('password')
  const strengthEl = document.getElementById('password-strength')

  // Carrega planos
  async function loadPlans() {
    try {
      const response = await api.getPlans({ active_only: 'true' })
      const urlPlanId = utils.getQueryParam('plan_id')

      planOptions.innerHTML = response.plans.map(plan => `
        <label class="plan-option ${plan.id === urlPlanId ? 'selected' : ''}" data-plan-id="${plan.id}">
          <input type="radio" name="plan" value="${plan.id}" ${plan.id === urlPlanId ? 'checked' : ''}>
          <div class="plan-option-content">
            <div class="plan-option-header">
              <strong>${utils.escapeHtml(plan.name)}</strong>
              <span class="plan-option-price">${utils.formatPrice(plan.price_cents, plan.currency)}/${plan.interval === 'year' ? 'ano' : 'mês'}</span>
            </div>
            <ul class="plan-option-features">
              ${plan.features.hd ? '<li>HD</li>' : ''}
              ${plan.features.full_hd ? '<li>Full HD</li>' : ''}
              ${plan.features['4k'] ? '<li>4K</li>' : ''}
              <li>${plan.max_simultaneous_streams} stream${plan.max_simultaneous_streams > 1 ? 's' : ''}</li>
              <li>${plan.max_devices} dispositivos</li>
            </ul>
          </div>
        </label>
      `).join('')

      // Seleção de plano
      planOptions.querySelectorAll('.plan-option').forEach(opt => {
        opt.addEventListener('click', () => {
          planOptions.querySelectorAll('.plan-option').forEach(o => o.classList.remove('selected'))
          opt.classList.add('selected')
          selectedPlanInput.value = opt.dataset.planId
        })
      })

      if (urlPlanId) selectedPlanInput.value = urlPlanId
    } catch (e) {
      console.error('Erro ao carregar planos:', e)
    }
  }

  // Medidor de força da senha
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

  passwordInput.addEventListener('input', () => {
    const { score, label, color } = checkPasswordStrength(passwordInput.value)
    strengthEl.innerHTML = `<div class="strength-bar"><div class="strength-fill" style="width: ${(score/5)*100}%; background: ${color}"></div></div><span style="color:${color}">${label}</span>`
  })

  loadPlans()

  registerForm.addEventListener('submit', async e => {
    e.preventDefault()
    const formData = new FormData(registerForm)
    const submitBtn = document.getElementById('submit-btn')
    const btnText = submitBtn.querySelector('.btn-text')
    const btnLoading = submitBtn.querySelector('.btn-loading')

    // Validações
    if (formData.get('password') !== formData.get('confirm_password')) {
      showError(registerForm, 'Senhas não coincidem')
      return
    }
    if (!selectedPlanInput.value) {
      showError(registerForm, 'Selecione um plano')
      return
    }

    submitBtn.disabled = true
    btnText.hidden = true
    btnLoading.hidden = false

    try {
      await auth.register({
        email: formData.get('email'),
        password: formData.get('password'),
        full_name: formData.get('full_name'),
        phone: formData.get('phone'),
        plan_id: selectedPlanInput.value,
      })

      // Redireciona para checkout
      const subscription = await api.getMySubscriptions()
      const pending = subscription.find(s => s.status === 'pending')
      if (pending) {
        window.location.href = `account.html?checkout=${pending.id}`
      } else {
        window.location.href = 'account.html'
      }
    } catch (error) {
      showError(registerForm, error.message)
    } finally {
      submitBtn.disabled = false
      btnText.hidden = false
      btnLoading.hidden = true
    }
  })
}

function showError(form, message) {
  // Remove erro anterior
  const existing = form.querySelector('.form-error')
  if (existing) existing.remove()

  const errorDiv = document.createElement('div')
  errorDiv.className = 'form-error'
  errorDiv.textContent = message
  form.insertBefore(errorDiv, form.firstChild)

  // Remove após 5s
  setTimeout(() => errorDiv.remove(), 5000)
}