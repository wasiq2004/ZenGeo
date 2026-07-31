import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { ApiError, api } from '@/lib/api'

interface ResetResult {
  email: string
  new_password: string
  sessions_revoked: number
  detail: string
}

/**
 * Account recovery.
 *
 * This deployment sends no email, so there is no self-service "forgot
 * password" flow — an administrator setting a password here is the only way
 * back into a locked-out account. The value is shown once, in the response,
 * and is stored only as a hash, so it cannot be retrieved afterwards.
 */
export function ResetPasswordCard({ userId, email }: { userId: string; email: string }) {
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ResetResult | null>(null)

  const reset = useMutation({
    mutationFn: () =>
      api.post<ResetResult>(`/admin/users/${userId}/reset-password`, {
        new_password: password,
        reason,
      }),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      setPassword('')
      setReason('')
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not reset the password.'),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound aria-hidden="true" className="size-4" />
          Reset password
        </CardTitle>
        <CardDescription>
          There is no email-based reset on this deployment, so this is the only way to recover{' '}
          <span className="font-medium text-foreground">{email}</span>. Every existing session is
          signed out at the same time.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {result ? (
          <Alert variant="success" title="Password updated">
            <p className="mb-2">
              {result.sessions_revoked} session(s) signed out. Give this password to the user over
              a channel you trust — it cannot be shown again.
            </p>
            <code className="block select-all rounded-md bg-foreground/10 px-3 py-2 font-mono text-sm">
              {result.new_password}
            </code>
            <Button
              variant="link"
              size="sm"
              className="mt-2 h-auto p-0"
              onClick={() => setResult(null)}
            >
              Done
            </Button>
          </Alert>
        ) : (
          <form
            className="max-w-sm space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              reset.mutate()
            }}
          >
            {error && <Alert variant="error">{error}</Alert>}

            <div className="space-y-1.5">
              <label htmlFor="new-password" className="text-sm font-medium">
                New password
              </label>
              <Input
                id="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 12 characters"
                autoComplete="new-password"
                minLength={12}
                required
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="reset-reason" className="text-sm font-medium">
                Reason <span className="text-muted-foreground">(recorded in the audit log)</span>
              </label>
              <Input
                id="reset-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Locked out, verified by phone"
                maxLength={300}
              />
            </div>

            <Button type="submit" variant="destructive" loading={reset.isPending}>
              Set new password
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
