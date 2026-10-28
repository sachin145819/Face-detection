import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '../api/index.js'
import { setUnauthorizedHandler } from '../api/client.js'
import { getToken, setToken } from '../lib/token.js'
import { useToast } from './ToastContext.jsx'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setTokenState] = useState(() => getToken())
  const [initializing, setInitializing] = useState(() => Boolean(getToken()))
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const locationRef = useRef(location)
  locationRef.current = location

  const applySession = useCallback((data) => {
    setToken(data.access_token)
    setTokenState(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setTokenState(null)
    setUser(null)
  }, [])

  // Any 401 from the API -> drop the session and send the user to /login.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      const hadSession = Boolean(getToken())
      logout()
      const { pathname, search } = locationRef.current
      if (pathname !== '/login') {
        if (hadSession) toast.error('Your session has expired. Please sign in again.')
        navigate('/login', { replace: true, state: { from: pathname + search } })
      }
    })
    return () => setUnauthorizedHandler(null)
  }, [logout, navigate, toast])

  // Restore the session on first load.
  useEffect(() => {
    let cancelled = false
    if (!getToken()) {
      setInitializing(false)
      return
    }
    authApi
      .me()
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .catch(() => {
        if (!cancelled) logout()
      })
      .finally(() => {
        if (!cancelled) setInitializing(false)
      })
    return () => {
      cancelled = true
    }
  }, [logout])

  const login = useCallback(
    async (email, password) => applySession(await authApi.login({ email, password })),
    [applySession],
  )

  const register = useCallback(
    async (name, email, password) => applySession(await authApi.register({ name, email, password })),
    [applySession],
  )

  const value = useMemo(
    () => ({ user, token, initializing, login, register, logout }),
    [user, token, initializing, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
