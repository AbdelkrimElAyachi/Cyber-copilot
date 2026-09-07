import { api } from './client.js'

export const chatApi = {
  listSessions: () => api.get('/chat/sessions'),
  createSession: (title) => api.post('/chat/sessions', title ? { title } : {}),
  getSession: (id) => api.get(`/chat/sessions/${id}`),
  renameSession: (id, title) => api.patch(`/chat/sessions/${id}`, { title }),
  deleteSession: (id) => api.delete(`/chat/sessions/${id}`),
  listMessages: (id) => api.get(`/chat/sessions/${id}/messages`),

  // Blocks until the assistant replies (it may call tools internally) —
  // there's no polling here, just a plain request/response.
  sendMessage: (id, content) => api.post(`/chat/sessions/${id}/messages`, { content }),
}
