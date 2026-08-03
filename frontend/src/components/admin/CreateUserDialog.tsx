import { useState } from 'react'
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
import { ApiError, api } from '@/lib/api'
import { useToast } from '@/components/ui/toast'
import type { AdminUserRow } from '@/lib/types'

/**
 * Create an account on someone's behalf.
 *
 * No mail leaves this deployment, so there is no invitation to send: the admin
 * sets the password here and passes it on out of band. The account is usable
 * from the moment it is created.
 */
export function CreateUserDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [makeAdmin, setMakeAdmin] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const reset = () => {
    setEmail('')
    setFullName('')
    setPassword('')
    setMakeAdmin(false)
    setError(null)
  }

  const create = useMutation({
    mutationFn: () =>
      api.post<AdminUserRow>('/admin/users', {
        email,
        password,
        full_name: fullName || null,
        role: makeAdmin ? 'admin' : 'user',
      }),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      toast({
        title: `Created ${user.email}`,
        description: 'Give them the password directly — it is not shown again.',
        variant: 'success',
      })
      reset()
      onOpenChange(false)
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not create the account.'),
  })

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
          <DialogTitle>Add a user</DialogTitle>
          <DialogDescription>
            The account works immediately — there is no confirmation email. Hand the password over
            yourself; it is not stored in readable form and cannot be shown again.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            create.mutate()
          }}
        >
          {error && <Alert variant="error">{error}</Alert>}

          <div className="space-y-1.5">
            <label htmlFor="new-user-email" className="text-sm font-medium">
              Email
            </label>
            <Input
              id="new-user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="new-user-name" className="text-sm font-medium">
              Name <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="new-user-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              maxLength={200}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="new-user-password" className="text-sm font-medium">
              Password
            </label>
            <Input
              id="new-user-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 12 characters"
              autoComplete="new-password"
              minLength={12}
              required
            />
          </div>

          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={makeAdmin}
              onChange={(e) => setMakeAdmin(e.target.checked)}
            />
            <span>
              Make this an administrator
              <span className="block text-xs text-muted-foreground">
                Full access to every user, audit and report, and to this panel.
              </span>
            </span>
          </label>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create account
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
