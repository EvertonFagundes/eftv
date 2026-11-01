// plans-page.js - Página de planos
import { api } from './api.js'
import { auth } from './auth.js'
import { utils } from './utils.js'

async function loadPlans() {
  const grid = document.getElementById('plans-grid')
  if (!grid) return

  grid.innerHTML = '<div class="loading">Carregando planos...</div>'

  try {
    const response = await api.getPlans({ active_only: 'true' })
    grid.innerHTML = response.plans.map(plan => `
      <article class="plan-card ${plan.sort_order === 1 ? 'popular' : ''}">
        ${plan.sort_order === 1 ? '<div class="plan-badge">Mais popular</div>' : ''}
        <header class="plan-header">
          <h3>${utils.escapeHtml(plan.name)}</h3>
          <div class="plan-price">
            <span class="plan-amount">${utils.formatPrice(plan.price_cents, plan.currency)}</span>
            <span class="plan-period">/${plan.interval === 'year' ? 'ano' : 'mês'}</span>
          </div>
          ${plan.description ? `<p class="plan-desc">${utils.escapeHtml(plan.description)}</p>` : ''}
        </header>
        <ul class="plan-features">
          ${plan.features.hd ? '<li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>Qualidade HD</li>' : ''}
          ${plan.features.full_hd ? '<li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>Full HD (1080p)</li>' : ''}
          ${plan.features['4k'] ? '<li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>4K Ultra HD</li>' : ''}
          <li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>${plan.max_simultaneous_streams} stream${plan.max_simultaneous_streams > 1 ? 's' : ''} simultâneo${plan.max_simultaneous_streams > 1 ? 's' : ''}</li>
          <li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>${plan.max_devices} dispositivos cadastrados</li>
          <li><svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 6L9 17l-5-5"/></svg>Cancelamento a qualquer momento</li>
        </ul>
        <a href="register.html?plan_id=${plan.id}" class="btn ${plan.sort_order === 1 ? 'btn-primary' : 'btn-outline'} btn-block">
          ${auth.isAuthenticated ? 'Trocar para este plano' : 'Assinar agora'}
        </a>
      </article>
    `).join('')
  } catch (e) {
    console.error('Erro ao carregar planos:', e)
    grid.innerHTML = '<div class="error">Erro ao carregar planos. Tente novamente.</div>'
  }
}

document.addEventListener('DOMContentLoaded', loadPlans)