import { api } from './client.js'
import { mock } from './mock.js'

export const usersApi = {
  async list(params = {}) {
    try {
      return await api.get('/users', params)
    } catch {
      return mock.users
    }
  },

  async get(id) {
    try {
      return await api.get(`/users/${id}`)
    } catch {
      return mock.users.find(u => u.id === id) || null
    }
  },
}
