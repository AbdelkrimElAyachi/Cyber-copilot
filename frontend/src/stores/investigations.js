import { defineStore } from 'pinia'
import { investigationsApi } from '../api/investigations.js'

export const useInvestigationsStore = defineStore('investigations', {
  state: () => ({
    investigations: [],
    currentInvestigation: null,
    evidence: [],
    analysis: [],
    actions: [],
    loading: false,
    error: null,
    filters: {
      status: '',
      severity: '',
    },
  }),

  getters: {
    filteredInvestigations(state) {
      return state.investigations.filter(inv => {
        if (state.filters.status && inv.status !== state.filters.status) return false
        if (state.filters.severity && inv.severity !== state.filters.severity) return false
        return true
      })
    },

    stats(state) {
      const inv = state.investigations
      return {
        total: inv.length,
        queued: inv.filter(i => i.status === 'QUEUED').length,
        investigating: inv.filter(i => i.status === 'INVESTIGATING').length,
        closed: inv.filter(i => i.status === 'CLOSED').length,
        critical: inv.filter(i => i.severity === 'critical').length,
        high: inv.filter(i => i.severity === 'high').length,
        medium: inv.filter(i => i.severity === 'medium').length,
        low: inv.filter(i => i.severity === 'low').length,
      }
    },

    recentInvestigations(state) {
      return [...state.investigations]
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 5)
    },
  },

  actions: {
    async fetchInvestigations(params = {}) {
      this.loading = true
      this.error = null
      try {
        this.investigations = await investigationsApi.list(params)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    async fetchInvestigation(id) {
      this.loading = true
      this.error = null
      try {
        this.currentInvestigation = await investigationsApi.get(id)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    async updateInvestigation(id, data) {
      try {
        const updated = await investigationsApi.update(id, data)
        if (this.currentInvestigation?.id === id) {
          this.currentInvestigation = updated
        }
        const index = this.investigations.findIndex(i => i.id === id)
        if (index !== -1) {
          this.investigations[index] = updated
        }
        return updated
      } catch (err) {
        this.error = err.message
        throw err
      }
    },

    async fetchEvidence(investigationId) {
      try {
        this.evidence = await investigationsApi.getEvidence(investigationId)
      } catch (err) {
        this.error = err.message
      }
    },

    async fetchAnalysis(investigationId) {
      try {
        this.analysis = await investigationsApi.getAnalysis(investigationId)
      } catch (err) {
        this.error = err.message
      }
    },

    async fetchActions(investigationId) {
      try {
        this.actions = await investigationsApi.getActions(investigationId)
      } catch (err) {
        this.error = err.message
      }
    },

    async fetchInvestigationDetail(id) {
      await this.fetchInvestigation(id)
      if (this.currentInvestigation) {
        await Promise.all([
          this.fetchEvidence(id),
          this.fetchAnalysis(id),
          this.fetchActions(id),
        ])
      }
    },

    setFilter(key, value) {
      this.filters[key] = value
    },

    clearFilters() {
      this.filters = { status: '', severity: '' }
    },
  },
})
