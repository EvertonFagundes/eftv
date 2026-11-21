// main.js - Landing page (index.html)
import { api } from './api.js'
import { utils } from './utils.js'

// Carrega planos na home
async function loadPlansPreview() {
  try {
    const response = await api.getPlans({ active_only: 'true', page_size: 3 })
    const grid = document.getElementById('plans-grid')
    if (!grid) return

    grid.innerHTML = response.plans.map(plan => {
      const features = plan.features || {}
      const streams = Number(plan.max_simultaneous_streams) || 1
      const devices = Number(plan.max_devices) || 1
      return `
      <article class="plan-card">
        <header class="plan-header">
          <h3>${utils.escapeHtml(plan.name)}</h3>
          <div class="plan-price">
            <span class="plan-amount">${utils.formatPrice(plan.price_cents, plan.currency)}</span>
            <span class="plan-period">/mês</span>
          </div>
        </header>
        <ul class="plan-features">
          ${features.hd ? '<li>✓ Qualidade HD</li>' : ''}
          ${features.full_hd ? '<li>✓ Full HD</li>' : ''}
          ${features['4k'] ? '<li>✓ 4K</li>' : ''}
          <li>✓ ${streams} stream${streams > 1 ? 's' : ''} simultâneo${streams > 1 ? 's' : ''}</li>
          <li>✓ ${devices} dispositivo${devices > 1 ? 's' : ''}</li>
        </ul>
        <a href="register.html?plan_id=${encodeURIComponent(plan.id)}" class="btn btn-outline btn-block">Assinar</a>
      </article>`
    }).join('')
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

  if (!channels || !channels.length) {
    grid.innerHTML = '<p class="empty-state">Nenhum canal nesta categoria por enquanto.</p>'
    return
  }

  grid.innerHTML = channels.map(ch => `
    <article class="channel-card" data-slug="${utils.escapeHtml(ch.slug)}" tabindex="0" role="link">
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
    const abrir = () => {
      const destino = `player.html?channel=${encodeURIComponent(card.dataset.slug)}`
      window.location.href = `register.html?redirect=${encodeURIComponent(destino)}`
    }
    card.addEventListener('click', abrir)
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        abrir()
      }
    })
  })
}

async function filterChannels(categoryId) {
  const grid = document.getElementById('channels-grid')
  if (grid) grid.innerHTML = '<p class="empty-state">Carregando canais...</p>'
  try {
    const params = { page_size: 8, include_adult: false }
    if (categoryId) params.category_id = categoryId
    const response = await api.getChannels(params)
    renderChannels(response.channels)
    if (grid && grid.scrollIntoView) {
      grid.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  } catch (erro) {
    console.error('Erro ao filtrar canais:', erro)
    if (grid) grid.innerHTML = '<p class="empty-state">Não foi possível carregar os canais. Tente novamente.</p>'
  }
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