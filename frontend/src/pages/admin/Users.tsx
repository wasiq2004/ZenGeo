import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LogIn, LogOut, Search, Shield, ShieldOff, UserCheck, UserPlus, UserX } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CreateUserDialog } from '@/components/admin/CreateUserDialog'
import { ImpersonateDialog } from '@/components/admin/ImpersonateDialog'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState, Skeleton } from '@/components/ui/feedback'
import { Field, Input, Textarea } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/misc'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/toast'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatRelative, initials } from '@/lib/format'
import { PROVIDER_LABEL } from '@/lib/geo'
import type { AdminUserRow, Paginated, UserRole } from '@/lib/types'

interface PendingChange {
  user: AdminUserRow
  role?: UserRole
  isActive?: boolean
  title: string
  body: string
}

export default function AdminUsers() {
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [roleFilter, setRoleFilter] = useState<string>('all')
  const [pending, setPending] = useState<PendingChange | null>(null)
  const [reason, setReason] = useState('')

  const params = new URLSearchParams({ page: String(page), page_size: '25' })
  if (search) params.set('search', search)
  if (roleFilter !== 'all') params.set('role', roleFilter)

  const [creating, setCreating] = useState(false)
  const [impersonating, setImpersonating] = useState<AdminUserRow | null>(null)

  const usersQuery = useQuery({
    queryKey: ['admin-users', page, search, roleFilter],
    queryFn: () => api.get<Paginated<AdminUserRow>>(`/admin/users?${params}`),
    placeholderData: (previous) => previous,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    queryClient.invalidateQueries({ queryKey: ['admin-stats'] })
    queryClient.invalidateQueries({ queryKey: ['admin-activity'] })
  }

  const update = useMutation({
    mutationFn: (change: PendingChange) =>
      api.patch(`/admin/users/${change.user.id}`, {
        ...(change.role !== undefined ? { role: change.role } : {}),
        ...(change.isActive !== undefined ? { is_active: change.isActive } : {}),
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      invalidate()
      setPending(null)
      setReason('')
      toast({ title: 'User updated', variant: 'success' })
    },
    onError: (error) =>
      toast({
        title: 'Could not update that user',
        description: error instanceof ApiError ? error.message : undefined,
        variant: 'error',
      }),
  })

  const forceLogout = useMutation({
    mutationFn: (user: AdminUserRow) => api.post<{ detail: string }>(`/admin/users/${user.id}/force-logout`),
    onSuccess: (result) => {
      invalidate()
      toast({ title: result.detail, variant: 'success' })
    },
    onError: () => toast({ title: 'Could not revoke sessions', variant: 'error' }),
  })

  const users = usersQuery.data?.items ?? []
  const total = usersQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 25))

  return (
    <>
      <PageHeader
        title="Users"
        description={`${total} account${total === 1 ? '' : 's'}.`}
        actions={
          <Button onClick={() => setCreating(true)}>
            <UserPlus aria-hidden="true" /> Add user
          </Button>
        }
      />

      <CreateUserDialog open={creating} onOpenChange={setCreating} />
      <ImpersonateDialog
        user={impersonating}
        open={impersonating !== null}
        onOpenChange={(open) => !open && setImpersonating(null)}
      />

      {/* One filter row above everything it scopes. */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <form
          className="flex-1"
          onSubmit={(e) => {
            e.preventDefault()
            setPage(1)
            setSearch(searchInput)
          }}
        >
          <Field label="Search">
            {(props) => (
              <div className="relative">
                <Search
                  className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  {...props}
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Email or name"
                  className="pl-9"
                />
              </div>
            )}
          </Field>
        </form>
        <div className="w-full sm:w-44">
          <Field label="Role">
            {(props) => (
              <Select
                value={roleFilter}
                onValueChange={(value) => {
                  setPage(1)
                  setRoleFilter(value)
                }}
              >
                <SelectTrigger id={props.id}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All roles</SelectItem>
                  <SelectItem value="user">Users</SelectItem>
                  <SelectItem value="admin">Admins</SelectItem>
                </SelectContent>
              </Select>
            )}
          </Field>
        </div>
      </div>

      {usersQuery.isLoading && users.length === 0 ? (
        <Skeleton className="h-64 w-full" />
      ) : users.length === 0 ? (
        <EmptyState title="No users match that filter" />
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Audits</TableHead>
                  <TableHead>Providers</TableHead>
                  <TableHead>Last login</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => {
                  const isSelf = user.id === me?.id
                  return (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="flex items-center gap-2.5">
                          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-semibold text-primary">
                            {initials(user.full_name, user.email)}
                          </span>
                          <span className="min-w-0">
                            <Link
                              to={`/admin/users/${user.id}`}
                              className="block truncate font-medium hover:text-primary"
                            >
                              {user.full_name || user.email}
                            </Link>
                            <span className="block truncate text-xs text-muted-foreground">
                              {user.email}
                            </span>
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.role === 'admin' ? 'warning' : 'secondary'}>
                          {user.role}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.is_active ? 'success' : 'destructive'}>
                          {user.is_active ? 'Active' : 'Disabled'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{user.audit_count}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {user.api_key_providers.length === 0 ? (
                            <span className="text-xs text-muted-foreground">none</span>
                          ) : (
                            user.api_key_providers.map((provider) => (
                              <Badge key={provider} variant="outline" className="text-[10px]">
                                {PROVIDER_LABEL[provider]?.split(' ')[0] ?? provider}
                              </Badge>
                            ))
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {user.last_login_at ? formatRelative(user.last_login_at) : 'never'}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Tooltip
                            content={
                              isSelf
                                ? 'You cannot change your own role'
                                : user.role === 'admin'
                                  ? 'Demote to user'
                                  : 'Promote to admin'
                            }
                          >
                            <span>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                disabled={isSelf}
                                aria-label={
                                  user.role === 'admin' ? 'Demote to user' : 'Promote to admin'
                                }
                                onClick={() =>
                                  setPending({
                                    user,
                                    role: user.role === 'admin' ? 'user' : 'admin',
                                    title:
                                      user.role === 'admin'
                                        ? 'Demote this administrator?'
                                        : 'Promote to administrator?',
                                    body:
                                      user.role === 'admin'
                                        ? `${user.email} will lose access to the admin panel.`
                                        : `${user.email} will get full access to the admin panel, including every user and audit.`,
                                  })
                                }
                              >
                                {user.role === 'admin' ? (
                                  <ShieldOff aria-hidden="true" />
                                ) : (
                                  <Shield aria-hidden="true" />
                                )}
                              </Button>
                            </span>
                          </Tooltip>

                          <Tooltip
                            content={
                              isSelf
                                ? 'You cannot disable your own account'
                                : user.is_active
                                  ? 'Disable this account'
                                  : 'Re-enable this account'
                            }
                          >
                            <span>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                disabled={isSelf}
                                aria-label={user.is_active ? 'Disable account' : 'Enable account'}
                                onClick={() =>
                                  setPending({
                                    user,
                                    isActive: !user.is_active,
                                    title: user.is_active
                                      ? 'Disable this account?'
                                      : 'Re-enable this account?',
                                    body: user.is_active
                                      ? `${user.email} will be signed out everywhere and will not be able to sign in again.`
                                      : `${user.email} will be able to sign in again.`,
                                  })
                                }
                              >
                                {user.is_active ? (
                                  <UserX aria-hidden="true" />
                                ) : (
                                  <UserCheck aria-hidden="true" />
                                )}
                              </Button>
                            </span>
                          </Tooltip>

                          <Tooltip
                            content={
                              isSelf
                                ? 'You are already signed in as yourself'
                                : user.role === 'admin'
                                  ? 'Administrators cannot be impersonated'
                                  : `Sign in as ${user.email}`
                            }
                          >
                            <span>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                disabled={isSelf || user.role === 'admin' || !user.is_active}
                                aria-label={`Sign in as ${user.email}`}
                                onClick={() => setImpersonating(user)}
                              >
                                <LogIn aria-hidden="true" />
                              </Button>
                            </span>
                          </Tooltip>

                          <Tooltip content="Sign this user out of every device">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Force logout"
                              loading={
                                forceLogout.isPending && forceLogout.variables?.id === user.id
                              }
                              onClick={() => forceLogout.mutate(user)}
                            >
                              <LogOut aria-hidden="true" />
                            </Button>
                          </Tooltip>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <Dialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{pending?.title}</DialogTitle>
            <DialogDescription>{pending?.body}</DialogDescription>
          </DialogHeader>

          <Field
            label="Reason"
            hint="Recorded in the admin activity log alongside this change"
          >
            {(props) => (
              <Textarea
                {...props}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                placeholder="Support request #482"
              />
            )}
          </Field>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPending(null)}>
              Cancel
            </Button>
            <Button
              loading={update.isPending}
              onClick={() => pending && update.mutate(pending)}
              variant={pending?.isActive === false ? 'destructive' : 'default'}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <p className="mt-4 text-xs text-muted-foreground">
        Every change here is written to the activity log with your account, the target user and
        the reason you give.
      </p>
    </>
  )
}
