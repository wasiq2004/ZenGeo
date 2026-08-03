import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { UserCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { ApiError, api } from '@/lib/api'
import { useAuth } from '@/lib/auth'

interface ImpersonateResult {
  access_token: string
  expires_in: number
  detail: string
}

/**
 * "Sign in as this user", for reproducing a problem you cannot see from the
 * outside.
 *
 * The admin re-enters their own password every time. That is not ceremony: an
 * admin session left open on an unlocked laptop would otherwise be a key to
 * every account in the system, and re-authentication is what keeps the blast
 * radius of a borrowed session small.
 *
 * The API enforces the rest — 30-minute token, no impersonating other admins,
 * no account changes while impersonating — so nothing here is the security
 * boundary.
 */
export function ImpersonateCard({ userId, email, isAdmin }: {
  userId: string
  email: string
  isAdmin: boolean
}) {
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { startImpersonation } = useAuth()
  const navigate = useNavigate()

  const impersonate = useMutation({
    mutationFn: () =>
      api.post<ImpersonateResult>(`/admin/users/${userId}/impersonate`, {
        password,
        reason,
      }),
    onSuccess: async (data) => {
      setPassword('')
      setReason('')
      await startImpersonation(data.access_token, data.expires_in)
      navigate('/app', { replace: true })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not start the session.'),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <UserCheck aria-hidden="true" className="size-4" />
          Sign in as this user
        </CardTitle>
        <CardDescription>
          Opens their dashboard exactly as they see it, to reproduce a problem. Everything you do is
          written to the audit log against your name, the session expires after 30 minutes, and
          account changes — password, email, deletion — are refused while you are in it.
        </CardDescription>
      </CardHeader>

      <CardContent>
        {isAdmin ? (
          <Alert variant="warning" title="Administrators cannot be impersonated">
            Signing in as another admin would turn one compromised account into all of them. Use a
            password reset instead if they need help getting in.
          </Alert>
        ) : (
          <form
            className="max-w-sm space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              setError(null)
              impersonate.mutate()
            }}
          >
            {error && <Alert variant="error">{error}</Alert>}

            <div className="space-y-1.5">
              <label htmlFor="impersonate-password" className="text-sm font-medium">
                Confirm your own password
              </label>
              <Input
                id="impersonate-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="impersonate-reason" className="text-sm font-medium">
                Reason <span className="text-muted-foreground">(recorded in the audit log)</span>
              </label>
              <Input
                id="impersonate-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Investigating a failed audit they reported"
                maxLength={300}
              />
            </div>

            <Button type="submit" loading={impersonate.isPending}>
              Sign in as {email}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
