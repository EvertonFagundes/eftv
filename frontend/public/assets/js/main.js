// main.js - Landing page (index.html)
import { api } from './api.js'
import { utils } from './utils.js'

// Carrega planos na home
async function loadPlansPreview() {
  try {
    const response = await api.getPlans({ active_only: 'true', page_size: 3 })
    const grid = document.getElementById('plans-grid')
    if (!grid) return

    grid.innerHTML = response.plans.map(plan => `
      <article class="plan-card">
        <header class="plan-header">
          <h3>${utils.escapeHtml(plan.name)}</h3>
          <div class="plan-price">
            <span class="plan-amount">${utils.formatPrice(plan.price_cents, plan.currency)}</span>
            <span class="plan-period">/mês</span>
          </div>
        </header>
        <ul class="plan-features">
          ${plan.features.hd ? '<li>✓ Qualidade HD</li>' : ''}
          ${plan.features.full_hd ? '<li>✓ Full HD</li>' : ''}
          ${plan.features['4k'] ? '<li>✓ 4K</li>' : ''}
          <li>✓ ${plan.max_simultaneous_streams} stream${plan.max_simultaneous_streams > 1 ? 's' : ''} simultâneo${plan.max_simultaneous_streams > 1 ? 's' : ''}</li>
          <li>✓ ${plan.max_devices} dispositivos</li>
        </ul>
        <a href="register.html?plan_id=${plan.id}" class="btn btn-outline btn-block">Assinar</a>
      </article>
    `).join('')
  } catch (e) {
    console.error('Erro ao carregar planos:', e)
  }
}

// Carrega categorias e canais preview
async function loadChannelsPreview() {
  try {
    const [categoriesRes, channelsRes] = await Promise.all([
      api.getCategories(),
      api.getChannels({ page_size: 8, include_adult: false }),
    ])

    // Chips de categoria
    const chipsContainer = document.getElementById('categories-chips')
    if (chipsContainer) {
      chipsContainer.innerHTML = `
        <button class="chip is-active" data-category="">Todos</button>
        ${categoriesRes.map(cat => `
          <button class="chip" data-category="${cat.id}">${utils.escapeHtml(cat.icon || '📺')} ${utils.escapeHtml(cat.name)}</button>
        `).join('')}
      `

      chipsContainer.addEventListener('click', e => {
        const btn = e.target.closest('.chip')
        if (!btn) return
        chipsContainer.querySelectorAll('.chip').forEach(b => b.classList.remove('is-active'))
        btn.classList.add('is-active')
        filterChannels(btn.dataset.category)
      })
    }

    // Grid de canais
    renderChannels(channelsRes.channels)

  } catch (e) {
    console.error('Erro ao carregar canais:', e)
  }
}

function renderChannels(channels) {
  const grid = document.getElementById('channels-grid')
  if (!grid) return

  grid.innerHTML = channels.map(ch => `
    <article class="channel-card" data-slug="${utils.escapeHtml(ch.slug)}">
      ${ch.logo_url ? `<img class="channel-logo" src="${utils.escapeHtml(ch.logo_url)}" alt="${utils.escapeHtml(ch.name)}" loading="lazy">` : '<div class="channel-logo-placeholder">📺</div>'}
      <div class="channel-info">
        <h4>${utils.escapeHtml(ch.name)}</h4>
        <span class="channel-badges">
          ${ch.is_live ? '<span class="badge live">AO VIVO</span>' : '<span class="badge vod">SOB DEMANDA</span>'}
          ${ch.is_adult ? '<span class="badge adult">18+</span>' : ''}
        </span>
      </div>
    </article>
  `).join('')

  grid.querySelectorAll('.channel-card').forEach(card => {
    card.addEventListener('click', () => {
      window.location.href = `register.html?redirect=player.html%3Fchannel=${card.dataset.slug}`
    })
  })
}

function filterChannels(categoryId) {
  // TODO: implementar filtro via API
  console.log('Filtrar por categoria:', categoryId)
}

// Inicialização
document.addEventListener('DOMContentLoaded', () => {
  loadPlansPreview()
  loadChannelsPreview()

  // Smooth scroll para links internos
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', e => {
      const target = document.querySelector(anchor.getAttribute('href'))
      if (target) {
        e.preventDefault()
        target.scrollIntoView({ behavior: 'smooth' })
      }
    })
  })
})