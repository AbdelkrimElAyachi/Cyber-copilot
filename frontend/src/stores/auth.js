import { defineStore } from 'pinia'
import { authApi } from '../api/auth'
import { getToken, setToken, clearToken } from '../api/token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: getToken(),
    loading: false,
    error: null,
    // Whether we've tried to resolve a stored token into a user yet —
    // lets the router guard tell "still checking" apart from "logged out".
    initialized: false,
  }),

  getters: {
    isAuthenticated: (state) => !!state.user,
  },

  actions: {
    async login(username, password) {
      this.loading = true
      this.error = null
      try {
        const data = await authApi.login(username, password)
        setToken(data.access_token)
        this.token = data.access_token
        this.user = data.user
        return true
      } catch (e) {
        this.error = e.status === 401
          ? 'Invalid username or password.'
          : (e.message || 'Login failed.')
        return false
      } finally {
        this.loading = false
      }
    },

    logout() {
      clearToken()
      this.token = null
      this.user = null
    },

    // Resolve a token already in storage (page reload / fresh tab) into
    // a user, or drop it if it's no longer valid. Safe to call once at
    // app startup regardless of whether a token exists.
    async fetchMe() {
      if (!this.token) {
        this.initialized = true
        return
      }
      try {
        this.user = await authApi.me()
      } catch {
        this.logout()
      } finally {
        this.initialized = true
      }
    },
  },
})
