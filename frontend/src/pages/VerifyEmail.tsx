import { CheckCircle2, XCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/feedback'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'

type State = 'verifying' | 'success' | 'error'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { isAuthenticated, refreshUser } = useAuth()
  const token = searchParams.get('token') ?? ''
  const [state, setState] = useState<State>(token ? 'verifying' : 'error')
  const [message, setMessage] = useState('This confirmation link is incomplete.')
  // Verification tokens are single-use; React 18 StrictMode double-invokes
  // effects in dev, which would burn the token on the first render.
  const attempted = useRef(false)

  useEffect(() => {
    if (!token || attempted.current) return
    attempted.current = true

    ;(async () => {
      try {
        await api.post('/auth/verify-email', { token })
        setState('success')
        if (isAuthenticated) await refreshUser().catch(() => undefined)
      } catch (error) {
        setState('error')
        setMessage(
          error instanceof ApiError
            ? error.message
            : 'We could not confirm this link. Request a new one from Settings.',
        )
      }
    })()
  }, [token, isAuthenticated, refreshUser])

  if (state === 'verifying') {
    return (
      <AuthLayout title="Confirming your email">
        <div className="flex flex-col items-center gap-3 py-4 text-sm text-muted-foreground">
          <Spinner className="size-6" />
          <p>One moment…</p>
        </div>
      </AuthLayout>
    )
  }

  if (state === 'success') {
    return (
      <AuthLayout title="Email confirmed">
        <div className="space-y-5 text-center">
          <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden="true" />
          <p className="text-sm leading-relaxed text-muted-foreground">
            Your address is confirmed. You can run audits now.
          </p>
          <Button className="w-full" onClick={() => navigate(isAuthenticated ? '/app' : '/login')}>
            {isAuthenticated ? 'Go to dashboard' : 'Sign in'}
          </Button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Link not valid">
      <div className="space-y-5 text-center">
        <XCircle className="mx-auto size-10 text-destructive" aria-hidden="true" />
        <p className="text-sm leading-relaxed text-muted-foreground">{message}</p>
        <Button asChild variant="outline" className="w-full">
          <Link to={isAuthenticated ? '/app/settings' : '/login'}>
            {isAuthenticated ? 'Request a new link' : 'Back to sign in'}
          </Link>
        </Button>
      </div>
    </AuthLayout>
  )
}
