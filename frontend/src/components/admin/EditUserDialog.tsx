import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
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
import type { AdminUserRow, UserRole } from '@/lib/types'

/**
 * Role and access, in one place.
 *
 * These used to be two separate icon buttons in the row, each with its own
 * confirmation. Both change the same thing — what this account is allowed to
 * do — so they belong on one form, where the admin can see the current state
 * of both before changing either.
 *
 * Deletion is deliberately NOT here: it is irreversible and lives behind its
 * own typed confirmation.
 */
export function EditUserDialog({
  user,
  open,
  onOpenChange,
}: {
  user: AdminUserRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [role, setRole] = useState<UserRole>('user')
  const [isActive, setIsActive] = useState(true)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Re-seed whenever a different row is opened, so the form always shows the
  // account's real current state rather than the last one edited.
  useEffect(() => {
    if (user) {
      setRole(user.role)
      setIsActive(user.is_active)
      setReason('')
      setError(null)
    }
  }, [user])

  const save = useMutation({
    mutationFn: () =>
      api.patch<AdminUserRow>(`/admin/users/${user?.id}`, {
        role,
        is_active: isActive,
        reason: reason || null,
      }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
      queryClient.invalidateQueries({ queryKey: ['admin-user', updated.id] })
      toast({ title: `Updated ${updated.email}`, variant: 'success' })
      onOpenChange(false)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not save those changes.'),
  })

  if (!user) return null

  const roleChanged = role !== user.role
  const accessChanged = isActive !== user.is_active

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit {user.email}</DialogTitle>
          <DialogDescription>
            Change what this account may do. Both changes are written to the admin audit log.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            save.mutate()
          }}
        >
          {error && <Alert variant="error">{error}</Alert>}

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Role</legend>
            {(['user', 'admin'] as const).map((value) => (
              <label key={value} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="role"
                  className="mt-0.5"
                  checked={role === value}
                  onChange={() => setRole(value)}
                />
                <span>
                  {value === 'admin' ? 'Administrator' : 'User'}
                  <span className="block text-xs text-muted-foreground">
                    {value === 'admin'
                      ? 'Full access to every user, audit and report, and to this panel.'
                      : 'Can run audits and see only their own data.'}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Access</legend>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <span>
                Account is enabled
                <span className="block text-xs text-muted-foreground">
                  Unchecking signs them out everywhere and blocks sign-in. Their audits and reports
                  are kept, and this is reversible.
                </span>
              </span>
            </label>
          </fieldset>

          <div className="space-y-1.5">
            <label htmlFor="edit-user-reason" className="text-sm font-medium">
              Reason <span className="text-muted-foreground">(recorded in the audit log)</span>
            </label>
            <Input
              id="edit-user-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Promoted to handle support"
              maxLength={500}
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!roleChanged && !accessChanged}
              loading={save.isPending}
            >
              Save changes
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
