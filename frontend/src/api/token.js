// Tiny standalone token holder — kept separate from stores/auth.js so
// api/client.js can read/clear it without importing the Pinia store
// (which itself needs client.js's `api`, and would create a cycle).

const STORAGE_KEY = 'cyber_copilot_token'

export function getToken() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(STORAGE_KEY, token)
  } catch {
    // Storage unavailable (private mode, etc.) — session just won't
    // survive a reload; not worth failing login over.
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}
