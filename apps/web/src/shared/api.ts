const API_BASE = (import.meta.env.VITE_API_URL ?? '/api/v1').replace(/\/$/, '')
const SESSION_KEY = 'anti-bagu:web-session:v1'

export interface AuthUser {
  id: string
  username: string
  display_name: string
  role: 'user' | 'admin'
  status: string
  created_at: string
}

export interface StoredSession {
  token: string
  expiresAt: string
  user: AuthUser
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

export function loadSession(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredSession
    if (!parsed.token || new Date(parsed.expiresAt).getTime() <= Date.now()) {
      window.sessionStorage.removeItem(SESSION_KEY)
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function saveSession(session: StoredSession | null): void {
  try {
    if (session) {
      window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
    } else {
      window.sessionStorage.removeItem(SESSION_KEY)
    }
  } catch {
    // Private browsing or a disabled storage backend should not crash login.
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  token = loadSession()?.token,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const body = await response.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    if (response.status === 401) saveSession(null)
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function websocketUrl(path: string, token?: string): string {
  const configured = import.meta.env.VITE_WS_BASE_URL as string | undefined
  const base = configured
    ? configured.replace(/\/$/, '')
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  const url = new URL(`${base}${path}`)
  if (token) url.searchParams.set('token', token)
  return url.toString()
}
