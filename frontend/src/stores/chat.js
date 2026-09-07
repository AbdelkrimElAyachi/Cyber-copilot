import { defineStore } from 'pinia'
import { chatApi } from '../api/chat.js'

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [],
    currentSessionId: null,
    messages: [],
    loadingSessions: false,
    loadingMessages: false,
    sending: false,
    error: null,
  }),

  getters: {
    currentSession(state) {
      return state.sessions.find(s => s.id === state.currentSessionId) || null
    },
  },

  actions: {
    async fetchSessions() {
      this.loadingSessions = true
      this.error = null
      try {
        this.sessions = await chatApi.listSessions()
      } catch (err) {
        this.error = err.message
      } finally {
        this.loadingSessions = false
      }
    },

    async createSession(title) {
      this.error = null
      const session = await chatApi.createSession(title)
      this.sessions.unshift(session)
      this.currentSessionId = session.id
      this.messages = []
      return session
    },

    async selectSession(id) {
      this.error = null
      this.currentSessionId = id
      await this.fetchMessages(id)
    },

    async fetchMessages(id) {
      this.loadingMessages = true
      this.error = null
      try {
        this.messages = await chatApi.listMessages(id)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loadingMessages = false
      }
    },

    async sendMessage(content) {
      const sessionId = this.currentSessionId
      if (!sessionId) return

      // Optimistic user bubble — the backend blocks until the assistant
      // replies, so show the question immediately instead of waiting.
      this.messages.push({
        id: `pending-${Date.now()}`,
        session_id: sessionId,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      })

      this.sending = true
      this.error = null
      try {
        const reply = await chatApi.sendMessage(sessionId, content)
        if (this.currentSessionId === sessionId) {
          this.messages.push(reply)
        }
        const session = this.sessions.find(s => s.id === sessionId)
        if (session) {
          session.updated_at = reply.created_at
          // Reflect the backend's auto-title (set from the first message)
          // without a round trip.
          if (this.messages.filter(m => m.role === 'user').length === 1) {
            const fresh = await chatApi.getSession(sessionId)
            session.title = fresh.title
          }
          this.sessions.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
        }
      } catch (err) {
        this.error = err.message || 'Failed to send message.'
        throw err
      } finally {
        this.sending = false
      }
    },

    async renameSession(id, title) {
      const updated = await chatApi.renameSession(id, title)
      const session = this.sessions.find(s => s.id === id)
      if (session) session.title = updated.title
    },

    async deleteSession(id) {
      await chatApi.deleteSession(id)
      this.sessions = this.sessions.filter(s => s.id !== id)
      if (this.currentSessionId === id) {
        this.currentSessionId = null
        this.messages = []
      }
    },
  },
})
