import { getToken, clearToken } from './token'

const API_BASE = '/api'

class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const token = getToken()
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  }

  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body)
  }

  try {
    const response = await fetch(url, config)

    if (response.status === 204) {
      return null
    }

    const data = await response.json()

    if (!response.ok) {
      if (response.status === 401 && path !== '/auth/login') {
        // Token missing/expired/invalid — drop it and let the app react
        // (router guard in main.js sends the user to /login). Not fired
        // for a failed login attempt itself, which is a normal 401.
        clearToken()
        window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      }
      throw new ApiError(
        data.detail || 'Request failed',
        response.status,
        data
      )
    }

    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('Network error', 0, null)
  }
}

export const api = {
  get: (path, params) => {
    const query = params ? '?' + new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
    ).toString() : ''
    return request(`${path}${query}`)
  },
  post: (path, body) => request(path, { method: 'POST', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
}

export { ApiError }
