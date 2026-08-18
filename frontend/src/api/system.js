import { api } from './client.js'

export const systemApi = {
  async getPollerStatus() {
    try {
      return await api.get('/poller/status')
    } catch {
      return { status: 'unknown', message: 'Could not reach backend' }
    }
  },
}
