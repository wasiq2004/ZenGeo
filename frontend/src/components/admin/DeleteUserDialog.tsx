import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { TriangleAlert } from 'lucide-react'
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
import { useToast } from '@/components/ui/toast'
import { ApiError, api } from '@/lib/api'
import type { AdminUserRow } from '@/lib/types'

interface DeleteResult {
  email: string
  audits_deleted: number
  businesses_deleted: number
  reports_removed: number
}

/**
 * Permanent deletion, behind a typed confirmation.
 *
 * Retyping the address is deliberate friction. This cascades through every
 * business, audit and stored PDF the account owns, and there is no undo — a
 * single click in a row of icon buttons is the wrong shape for that.
 *
 * Disabling remains the reversible option and is one row up in the same menu.
 */
export function DeleteUserDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [confirmEmail, setConfirmEmail] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const reset = () => {
    setConfirmEmail('')
    setReason('')
    setError(null)
  }

  const remove = useMutation({
    mutationFn: () =>
      // api.delete takes RequestOptions, not a bare body.
      api.delete<DeleteResult>(`/admin/users/${user?.id}`, {
        body: { confirm_email: confirmEmail, reason },
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      toast({
        title: `Deleted ${data.email}`,
        description: `${data.audits_deleted} audit(s), ${data.businesses_deleted} business(es) and ${data.reports_removed} report(s) removed.`,
        variant: 'success',
      })
      reset()
      onOpenChange(false)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not delete the account.'),
  })

  if (!user) return null
  const matches = confirmEmail.trim().toLowerCase() === user.email.toLowerCase()

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        onOpenChange(next)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {user.email}?</DialogTitle>
          <DialogDescription>
            This removes the account and everything it owns — every business, audit and stored PDF
            report. Their reports will also disappear from your admin views. It cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            remove.mutate()
          }}
        >
          {error && <Alert variant="error">{error}</Alert>}

          <Alert variant="warning" title="Consider disabling instead">
            Disabling signs them out everywhere and blocks sign-in, but keeps their audit history
            for your records — and it is reversible.
          </Alert>

          <div className="space-y-1.5">
            <label htmlFor="delete-confirm-email" className="text-sm font-medium">
              Type <span className="font-mono">{user.email}</span> to confirm
            </label>
            <Input
              id="delete-confirm-email"
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              autoComplete="off"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="delete-reason" className="text-sm font-medium">
              Reason <span className="text-muted-foreground">(recorded in the audit log)</span>
            </label>
            <Input
              id="delete-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Account closure requested"
              maxLength={300}
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={!matches} loading={remove.isPending}>
              <TriangleAlert aria-hidden="true" /> Delete permanently
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
