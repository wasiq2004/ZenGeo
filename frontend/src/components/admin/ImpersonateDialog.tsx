import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { ApiError, api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import type { AdminUserRow } from '@/lib/types'

interface ImpersonateResult {
  access_token: string
  expires_in: number
}

/**
 * Password-confirm step for impersonating from the users list.
 *
 * Same contract as the card on the user detail page — the API is what enforces
 * the 30-minute token, the refusal to impersonate admins, and the block on
 * account changes. This is only the prompt.
 */
export function ImpersonateDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [password, setPassword] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const { startImpersonation } = useAuth()
  const navigate = useNavigate()

  const impersonate = useMutation({
    mutationFn: () =>
      api.post<ImpersonateResult>(`/admin/users/${user?.id}/impersonate`, { password, reason }),
    onSuccess: async (data) => {
      setPassword('')
      setReason('')
      setError(null)
      onOpenChange(false)
      await startImpersonation(data.access_token, data.expires_in)
      navigate('/app', { replace: true })
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not start the session.'),
  })

  if (!user) return null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setPassword('')
          setReason('')
          setError(null)
        }
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sign in as {user.email}?</DialogTitle>
          <DialogDescription>
            You will see their dashboard exactly as they do. The session lasts 30 minutes,
            everything you do is logged against your name, and password, email and deletion are
            blocked while you are in it.
          </DialogDescription>
        </DialogHeader>

        <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          setError(null)
          impersonate.mutate()
        }}
      >
        {error && <Alert variant="error">{error}</Alert>}

        <div className="space-y-1.5">
          <label htmlFor="row-impersonate-password" className="text-sm font-medium">
            Confirm your own password
          </label>
          <Input
            id="row-impersonate-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="row-impersonate-reason" className="text-sm font-medium">
            Reason <span className="text-muted-foreground">(recorded in the audit log)</span>
          </label>
          <Input
            id="row-impersonate-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Investigating a failed audit they reported"
            maxLength={300}
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" loading={impersonate.isPending}>
            Sign in as user
          </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
