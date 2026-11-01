// catalog.js - Catálogo de canais, busca, filtros
import { api } from './api.js'

export const catalog = {
  channels: [],
  categories: [],
  currentPage: 1,
  pageSize: 20,
  total: 0,
  filters: {
    search: '',
    category: '',
    isLive: null,
    includeAdult: false,
  },
  _listeners: new Set(),

  subscribe(listener) {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  },

  _notify() {
    this._listeners.forEach(fn => fn(this))
  },

  async loadCategories() {
    this.categories = await api.getCategories()
    this._notify()
  },

  async loadChannels(append = false) {
    const params = {
      page: this.currentPage,
      page_size: this.pageSize,
    }
    if (this.filters.search) params.search = this.filters.search
    if (this.filters.category) params.category_id = this.filters.category
    if (this.filters.isLive !== null) params.is_live = this.filters.isLive
    if (this.filters.includeAdult) params.include_adult = true

    const response = await api.getChannels(params)
    if (append) {
      this.channels.push(...response.channels)
    } else {
      this.channels = response.channels
    }
    this.total = response.total
    this._notify()
  },

  setFilter(key, value) {
    this.filters[key] = value
    this.currentPage = 1
  },

  setSearch(query) {
    this.setFilter('search', query)
  },

  setCategory(categoryId) {
    this.setFilter('category', categoryId)
  },

  setLiveOnly(liveOnly) {
    this.setFilter('isLive', liveOnly)
  },

  setIncludeAdult(include) {
    this.setFilter('includeAdult', include)
  },

  nextPage() {
    if (this.channels.length < this.total) {
      this.currentPage++
      this.loadChannels(true)
    }
  },

  reset() {
    this.channels = []
    this.currentPage = 1
    this.filters = { search: '', category: '', isLive: null, includeAdult: false }
  },

  // Helpers para renderização
  getCategoryName(categoryId) {
    const cat = this.categories.find(c => c.id === categoryId)
    return cat ? cat.name : categoryId
  },

  getCategoryIcon(categoryId) {
    const cat = this.categories.find(c => c.id === categoryId)
    return cat ? cat.icon || '📺' : '📺'
  },

  getCategoryColor(categoryId) {
    const cat = this.categories.find(c => c.id === categoryId)
    return cat ? cat.color || '#2f9bff' : '#2f9bff'
  },
}

export default catalog