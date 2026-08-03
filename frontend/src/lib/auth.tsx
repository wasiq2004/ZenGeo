/**
 * Authentication context.
 *
 * On boot the app tries a silent refresh: the httpOnly cookie is the only thing
 * that survives a reload, so exchanging it for an access token is how a session
 * is restored. Until that resolves, `isLoading` is true and protected routes
 * render nothing rather than flashing the login page.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api, refreshAccessToken, setAccessToken, setUnauthorizedHandler } from './api'
import type { TokenResponse, User } from './types'

/** What GET /auth/me returns: the account, plus who is acting as it. */
interface SessionState {
  user: User
  impersonated_by: string | null
}

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  isAdmin: boolean
  /** Set when an admin is signed in AS this user. Read from the token's `act`
   *  claim server-side, so the client cannot fake or clear it. */
  impersonatedBy: string | null
  startImpersonation: (token: string, expiresIn: number) => Promise<void>
  endImpersonation: () => Promise<void>
  login: (email: string, password: string, totpCode?: string) => Promise<User>
  signup: (email: string, password: string, fullName?: string) => Promise<User>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Refresh a minute before the token actually expires. */
const REFRESH_MARGIN_MS = 60_000

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)
  const [impersonatedBy, setImpersonatedBy] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const refreshTimer = useRef<number | undefined>(undefined)

  const clearSession = useCallback(() => {
    setAccessToken(null)
    setUserState(null)
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current)
  }, [])

  /** Keep the access token fresh while a tab stays open. */
  const scheduleRefresh = useCallback(
    (expiresInSeconds: number) => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current)
      const delay = Math.max(expiresInSeconds * 1000 - REFRESH_MARGIN_MS, 15_000)
      refreshTimer.current = window.setTimeout(async () => {
        const ok = await refreshAccessToken()
        if (ok) scheduleRefresh(expiresInSeconds)
        else clearSession()
      }, delay)
    },
    [clearSession],
  )

  const applySession = useCallback(
    (session: TokenResponse) => {
      setAccessToken(session.access_token)
      setUserState(session.user)
      scheduleRefresh(session.expires_in)
    },
    [scheduleRefresh],
  )

  // Restore the session on first mount.
  useEffect(() => {
    let cancelled = false
    setUnauthorizedHandler(clearSession)

    ;(async () => {
      const restored = await refreshAccessToken()
      if (cancelled) return
      if (restored) {
        try {
          const me = await api.get<SessionState>('/auth/me')
          if (!cancelled) {
            setUserState(me.user)
            setImpersonatedBy(me.impersonated_by)
            // Token TTL is 15 min server-side; re-arm on that cadence.
            scheduleRefresh(15 * 60)
          }
        } catch {
          if (!cancelled) clearSession()
        }
      }
      if (!cancelled) setIsLoading(false)
    })()

    return () => {
      cancelled = true
      setUnauthorizedHandler(null)
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current)
    }
  }, [clearSession, scheduleRefresh])

  const login = useCallback(
    async (email: string, password: string, totpCode?: string) => {
      const session = await api.post<TokenResponse>('/auth/login', {
        email,
        password,
        ...(totpCode ? { totp_code: totpCode } : {}),
      })
      applySession(session)
      return session.user
    },
    [applySession],
  )

  const signup = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const session = await api.post<TokenResponse>('/auth/signup', {
        email,
        password,
        ...(fullName ? { full_name: fullName } : {}),
      })
      applySession(session)
      return session.user
    },
    [applySession],
  )

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout', undefined, { withCsrf: true })
    } catch {
      // Even if the call fails, drop local state - the user asked to leave.
    }
    clearSession()
  }, [clearSession])

  const refreshUser = useCallback(async () => {
    const me = await api.get<SessionState>('/auth/me')
    setUserState(me.user)
    setImpersonatedBy(me.impersonated_by)
  }, [])

  /** Swap the admin's token for the impersonation token and adopt that session. */
  const startImpersonation = useCallback(
    async (token: string, expiresIn: number) => {
      setAccessToken(token)
      const me = await api.get<SessionState>('/auth/me')
      setUserState(me.user)
      setImpersonatedBy(me.impersonated_by)
      scheduleRefresh(expiresIn)
    },
    [scheduleRefresh],
  )

  /**
   * Leave the impersonated session.
   *
   * The refresh cookie was never replaced - only the in-memory access token
   * was - so exchanging it returns the admin to their own session without a
   * second login. That is also why the impersonation token is memory-only: a
   * page reload already drops back to the admin.
   */
  const endImpersonation = useCallback(async () => {
    setAccessToken(null)
    const restored = await refreshAccessToken()
    if (!restored) {
      clearSession()
      return
    }
    const me = await api.get<SessionState>('/auth/me')
    setUserState(me.user)
    setImpersonatedBy(me.impersonated_by)
    scheduleRefresh(15 * 60)
  }, [clearSession, scheduleRefresh])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      impersonatedBy,
      startImpersonation,
      endImpersonation,
      isLoading,
      isAuthenticated: user !== null,
      isAdmin: user?.role === 'admin',
      login,
      signup,
      logout,
      refreshUser,
      setUser: setUserState,
    }),
    [user, isLoading, login, signup, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
