import { api } from './client.js'

export const pollerApi = {
  getStatus() {
    return api.get('/poller/status')
  },

  start(config = {}) {
    return api.post('/poller/start', {
      interval: config.interval || 60,
      lookback_hours: config.lookback_hours || 24,
    })
  },

  stop() {
    return api.post('/poller/stop', {})
  },

  runOnce(config = {}) {
    return api.post('/poller/run-once', {
      lookback_hours: config.lookback_hours || 24,
    })
  },

  reset() {
    return api.post('/poller/reset', {})
  },

  saveConfig(config = {}) {
    return api.patch('/poller/config', {
      interval: config.interval || 60,
      lookback_hours: config.lookback_hours || 24,
    })
  },
}
