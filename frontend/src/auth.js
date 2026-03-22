const AUTH_TOKEN_KEY = 'auth_token'
const USER_INFO_KEY = 'user_info'

export function getStoredToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || ''
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_INFO_KEY)
  if (!raw) return null

  try {
    return JSON.parse(raw)
  } catch {
    clearAuthSession()
    return null
  }
}

export function hasAuthSession() {
  return Boolean(getStoredToken())
}

export function setAuthSession(token, user) {
  localStorage.setItem(AUTH_TOKEN_KEY, token)
  localStorage.setItem(USER_INFO_KEY, JSON.stringify(user))
}

export function clearAuthSession() {
  localStorage.removeItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(USER_INFO_KEY)
}
