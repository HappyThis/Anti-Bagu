import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  apiRequest,
  loadSession,
  saveSession,
  type AuthUser,
  type StoredSession,
} from '../shared/api'

interface LoginResponse {
  token: string
  expires_at: string
  user: AuthUser
}

interface AuthContextValue {
  session: StoredSession | null
  user: AuthUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<AuthUser>
  register: (activationKey: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(() => loadSession())
  const [loading, setLoading] = useState(session === null)

  useEffect(() => {
    if (session) {
      setLoading(false)
      return
    }
    let disposed = false
    apiRequest<AuthUser>('/auth/me', { credentials: 'same-origin' }, undefined)
      .then((user) => {
        if (!disposed) {
          setSession({ token: '', expiresAt: '', user })
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (!disposed) setLoading(false)
      })
    return () => {
      disposed = true
    }
  }, [session])

  const login = useCallback(async (username: string, password: string) => {
    const response = await apiRequest<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }, undefined)
    const next = {
      token: response.token,
      expiresAt: response.expires_at,
      user: response.user,
    }
    saveSession(next)
    setSession(next)
    return response.user
  }, [])

  const register = useCallback(async (activationKey: string, username: string, password: string) => {
    await apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        activation_key: activationKey,
        username,
        password,
      }),
    }, undefined)
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiRequest('/auth/logout', { method: 'POST' }, session?.token)
    } finally {
      saveSession(null)
      setSession(null)
    }
  }, [session?.token])

  const value = useMemo<AuthContextValue>(() => ({
    session,
    user: session?.user ?? null,
    loading,
    login,
    register,
    logout,
  }), [loading, login, logout, register, session])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
