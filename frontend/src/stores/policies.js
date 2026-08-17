import { defineStore } from 'pinia'
import { policiesApi } from '../api/policies.js'

export const usePoliciesStore = defineStore('policies', {
  state: () => ({
    policies: [],
    currentPolicy: null,
    loading: false,
    error: null,
  }),

  getters: {
    enabledPolicies(state) {
      return state.policies.filter(p => p.is_enabled)
    },

    sortedPolicies(state) {
      return [...state.policies].sort((a, b) => b.priority - a.priority)
    },
  },

  actions: {
    async fetchPolicies(params = {}) {
      this.loading = true
      this.error = null
      try {
        this.policies = await policiesApi.list(params)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    async fetchPolicy(id) {
      this.loading = true
      this.error = null
      try {
        this.currentPolicy = await policiesApi.get(id)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    async createPolicy(data) {
      try {
        const result = await policiesApi.create(data)
        await this.fetchPolicies()
        return result
      } catch (err) {
        this.error = err.message
        throw err
      }
    },

    async updatePolicy(id, data) {
      try {
        const updated = await policiesApi.update(id, data)
        const index = this.policies.findIndex(p => p.id === id)
        if (index !== -1) {
          this.policies[index] = updated
        }
        return updated
      } catch (err) {
        this.error = err.message
        throw err
      }
    },

    async togglePolicy(id, enabled) {
      return await this.updatePolicy(id, { is_enabled: enabled })
    },

    async removePolicy(id) {
      try {
        await policiesApi.remove(id)
        this.policies = this.policies.filter(p => p.id !== id)
      } catch (err) {
        this.error = err.message
        throw err
      }
    },
  },
})
