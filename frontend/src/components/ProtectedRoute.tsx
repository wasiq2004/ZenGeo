import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { LoadingScreen } from '@/components/ui/feedback'
import { useAuth } from '@/lib/auth'

/**
 * Client-side route guard.
 *
 * This is a routing convenience, not a security boundary - every protected
 * endpoint re-checks the role server-side. Its job is to avoid rendering a
 * panel the user cannot use and to remember where they were headed.
 */
export function ProtectedRoute({
  children,
  requireAdmin = false,
}: {
  children: ReactNode
  requireAdmin?: boolean
}) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth()
  const location = useLocation()

  // Until the silent refresh settles we cannot tell "signed out" from
  // "restoring", so render a spinner rather than flashing the login page.
  if (isLoading) return <LoadingScreen label="Restoring your session" />

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  if (requireAdmin && !isAdmin) {
    return <Navigate to="/app" replace />
  }

  return <>{children}</>
}

/** Sends an already-signed-in user away from /login and /signup. */
export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth()
  if (isLoading) return <LoadingScreen label="Restoring your session" />
  if (isAuthenticated) return <Navigate to={isAdmin ? '/admin' : '/app'} replace />
  return <>{children}</>
}
