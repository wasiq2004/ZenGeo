import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, KeyRound, ShieldAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, LoadingScreen } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { formatDateTime, formatRelative, formatScore } from '@/lib/format'
import { PROVIDER_LABEL, bandBadgeVariant } from '@/lib/geo'
import type { AdminUserRow } from '@/lib/types'

interface UserDetailResponse {
  user: AdminUserRow
  businesses: Array<{
    id: string
    name: string
    website_url: string
    industry: string | null
    created_at: string
  }>
  audits: Array<{
    id: string
    business_name: string
    status: string
    geo_score: number | null
    score_band: string | null
    created_at: string
    completed_at: string | null
  }>
  api_keys: Array<{
    provider: string
    label: string
    is_active: boolean
    created_at: string
    last_used_at: string | null
  }>
  admin_activity: Array<{
    action: string
    reason: string | null
    created_at: string
    metadata: Record<string, unknown>
  }>
}

export default function AdminUserDetail() {
  const { userId } = useParams<{ userId: string }>()

  const detailQuery = useQuery({
    queryKey: ['admin-user', userId],
    queryFn: () => api.get<UserDetailResponse>(`/admin/users/${userId}`),
  })

  if (detailQuery.isLoading) return <LoadingScreen label="Loading user" />
  if (detailQuery.isError || !detailQuery.data) {
    return (
      <>
        <PageHeader title="User" />
        <Alert variant="error" title="Could not load this user">
          They may have deleted their account.
        </Alert>
      </>
    )
  }

  const { user, businesses, audits, api_keys, admin_activity } = detailQuery.data

  return (
    <>
      <PageHeader
        title={user.full_name || user.email}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{user.email}</span>
            <Badge variant={user.role === 'admin' ? 'warning' : 'secondary'}>{user.role}</Badge>
            <Badge variant={user.is_active ? 'success' : 'destructive'}>
              {user.is_active ? 'Active' : 'Disabled'}
            </Badge>
            {!user.is_email_verified && <Badge variant="muted">Email unconfirmed</Badge>}
            {user.mfa_enabled && <Badge variant="outline">2FA on</Badge>}
          </span>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link to="/admin/users">
              <ArrowLeft aria-hidden="true" /> All users
            </Link>
          </Button>
        }
      />

      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">Joined</p>
              <p className="text-lg font-medium">{formatDateTime(user.created_at)}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">Last login</p>
              <p className="text-lg font-medium">
                {user.last_login_at ? formatRelative(user.last_login_at) : 'Never'}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">Audits run</p>
              <p className="text-lg font-medium tabular-nums">{user.audit_count}</p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4" aria-hidden="true" /> Connected API keys
            </CardTitle>
            <CardDescription>
              Which providers this user has connected. The keys themselves are encrypted at rest
              and there is no endpoint — here or anywhere — that returns them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {api_keys.length === 0 ? (
              <p className="text-sm text-muted-foreground">No keys connected.</p>
            ) : (
              <ul className="space-y-2">
                {api_keys.map((key, index) => (
                  <li
                    key={index}
                    className="flex flex-wrap items-center gap-2 rounded-md border border-border p-3 text-sm"
                  >
                    <span className="font-medium">
                      {PROVIDER_LABEL[key.provider] ?? key.provider}
                    </span>
                    <Badge variant="secondary">{key.label}</Badge>
                    {!key.is_active && <Badge variant="muted">Paused</Badge>}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {key.last_used_at
                        ? `last used ${formatRelative(key.last_used_at)}`
                        : 'never used'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Businesses ({businesses.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {businesses.length === 0 ? (
              <p className="text-sm text-muted-foreground">No businesses yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Website</TableHead>
                    <TableHead>Industry</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {businesses.map((business) => (
                    <TableRow key={business.id}>
                      <TableCell className="font-medium">{business.name}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {business.website_url}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {business.industry ?? '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Audits ({audits.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {audits.length === 0 ? (
              <p className="text-sm text-muted-foreground">No audits yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Business</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead>Run</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {audits.map((audit) => (
                    <TableRow key={audit.id}>
                      <TableCell className="font-medium">{audit.business_name}</TableCell>
                      <TableCell className="text-sm">{audit.status}</TableCell>
                      <TableCell className="text-right">
                        {audit.geo_score !== null ? (
                          <Badge variant={bandBadgeVariant(audit.geo_score)}>
                            {formatScore(audit.geo_score)}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatRelative(audit.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="size-4" aria-hidden="true" /> Admin actions on this account
            </CardTitle>
          </CardHeader>
          <CardContent>
            {admin_activity.length === 0 ? (
              <EmptyState title="No admin actions recorded" />
            ) : (
              <ol className="space-y-3">
                {admin_activity.map((entry, index) => (
                  <li key={index} className="flex gap-3 text-sm">
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatDateTime(entry.created_at)}
                    </span>
                    <span>
                      <span className="font-medium">{entry.action}</span>
                      {entry.reason && (
                        <span className="block text-muted-foreground">{entry.reason}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
