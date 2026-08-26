import { api } from './client.js'
import { mock } from './mock.js'

const USE_MOCK = false

export const investigationsApi = {
  async list(params = {}) {
    try {
      return await api.get('/investigations', params)
    } catch {
      if (USE_MOCK) return mock.investigations
      return mock.investigations
    }
  },

  async get(id) {
    try {
      return await api.get(`/investigations/${id}`)
    } catch {
      return mock.investigations.find(i => i.id === id) || null
    }
  },

  async update(id, data) {
    try {
      return await api.patch(`/investigations/${id}`, data)
    } catch {
      const inv = mock.investigations.find(i => i.id === id)
      return inv ? { ...inv, ...data } : null
    }
  },

  async delete(id) {
    return await api.delete(`/investigations/${id}`)
  },

  // Kicks off (or re-runs) the AI Investigator for this investigation.
  // Runs in the background on the server — errors (no AI configured,
  // already running, alert not found) are surfaced, not swallowed.
  async investigate(id) {
    return await api.post(`/investigations/${id}/investigate`, {})
  },

  async getEvidence(investigationId) {
    try {
      return await api.get(`/investigations/${investigationId}/evidence`)
    } catch {
      return mock.evidence[investigationId] || []
    }
  },

  async addEvidence(investigationId, data) {
    return await api.post(`/investigations/${investigationId}/evidence`, data)
  },

  async getAnalysis(investigationId) {
    try {
      return await api.get(`/investigations/${investigationId}/analysis`)
    } catch {
      return mock.analysis[investigationId] || []
    }
  },

  async addAnalysis(investigationId, data) {
    return await api.post(`/investigations/${investigationId}/analysis`, data)
  },

  async getActions(investigationId) {
    try {
      return await api.get(`/investigations/${investigationId}/actions`)
    } catch {
      return mock.actions[investigationId] || []
    }
  },

  async addAction(investigationId, data) {
    return await api.post(`/investigations/${investigationId}/actions`, data)
  },

  async updateAction(investigationId, actionId, data) {
    return await api.patch(`/investigations/${investigationId}/actions/${actionId}`, data)
  },
}
