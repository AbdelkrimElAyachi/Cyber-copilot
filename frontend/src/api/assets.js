import { api } from './client.js'
import { mock } from './mock.js'

export const assetsApi = {
  async list(params = {}) {
    try {
      return await api.get('/assets', params)
    } catch {
      return mock.assets
    }
  },

  async get(id) {
    try {
      return await api.get(`/assets/${id}`)
    } catch {
      return mock.assets.find(a => a.id === id) || null
    }
  },

  async create(data) {
    return await api.post('/assets', data)
  },

  async update(id, data) {
    return await api.patch(`/assets/${id}`, data)
  },

  async remove(id) {
    return await api.delete(`/assets/${id}`)
  },
}
