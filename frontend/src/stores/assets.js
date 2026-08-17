import { defineStore } from 'pinia'
import { assetsApi } from '../api/assets.js'

export const useAssetsStore = defineStore('assets', {
  state: () => ({
    assets: [],
    currentAsset: null,
    loading: false,
    error: null,
    filters: {
      asset_type: '',
      criticality: '',
    },
  }),

  getters: {
    filteredAssets(state) {
      return state.assets.filter(a => {
        if (state.filters.asset_type && a.asset_type !== state.filters.asset_type) return false
        if (state.filters.criticality && a.criticality !== state.filters.criticality) return false
        return true
      })
    },

    assetsByType(state) {
      const types = {}
      state.assets.forEach(a => {
        types[a.asset_type] = (types[a.asset_type] || 0) + 1
      })
      return types
    },
  },

  actions: {
    async fetchAssets(params = {}) {
      this.loading = true
      this.error = null
      try {
        this.assets = await assetsApi.list(params)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    async fetchAsset(id) {
      this.loading = true
      this.error = null
      try {
        this.currentAsset = await assetsApi.get(id)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    },

    setFilter(key, value) {
      this.filters[key] = value
    },

    clearFilters() {
      this.filters = { asset_type: '', criticality: '' }
    },
  },
})
