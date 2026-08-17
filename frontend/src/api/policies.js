import { api } from './client.js'
import { mock } from './mock.js'

export const policiesApi = {
  async list(params = {}) {
    try {
      return await api.get('/policies', params)
    } catch {
      return mock.policies
    }
  },

  async get(id) {
    try {
      return await api.get(`/policies/${id}`)
    } catch {
      return mock.policies.find(p => p.id === id) || null
    }
  },

  async create(data) {
    return await api.post('/policies', data)
  },

  async update(id, data) {
    try {
      return await api.patch(`/policies/${id}`, data)
    } catch {
      const policy = mock.policies.find(p => p.id === id)
      return policy ? { ...policy, ...data } : null
    }
  },

  async remove(id) {
    return await api.delete(`/policies/${id}`)
  },
}
