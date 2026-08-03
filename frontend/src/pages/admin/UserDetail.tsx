import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, KeyRound, ShieldAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ImpersonateCard } from '@/components/admin/ImpersonateCard'
import { ResetPasswordCard } from '@/components/admin/ResetPasswordCard'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, LoadingScreen } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api, apiDownload } from '@/lib/api'
import { useToast } from '@/components/ui/toast'
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
    has_report: boolean
  }>
  audit_summary: {
    total: number
    completed: number
    failed: number
    reports: number
    showing: number
  }
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

  const { toast } = useToast()

  // GET /reports/{id} has always permitted an administrator to fetch anyone's
  // report, and logs `admin_report_access` when it is not the owner asking.
  // This only surfaces that - it does not widen what an admin may reach.
  const download = useMutation({
    mutationFn: async (audit: { id: string; business_name: string }) => {
      const blob = await apiDownload(`/reports/${audit.id}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `checkgeo-${audit.business_name.replace(/\W+/g, '-').toLowerCase() || 'report'}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: () => toast({ title: 'Could not download that report', variant: 'error' }),
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

  const { user, businesses, audits, api_keys, admin_activity, audit_summary } = detailQuery.data

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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
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
              <p className="text-lg font-medium tabular-nums">{audit_summary.total}</p>
              <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
                {audit_summary.completed} completed · {audit_summary.failed} failed
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">PDF reports</p>
              <p className="text-lg font-medium tabular-nums">{audit_summary.reports}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Downloadable below</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-5">
              <p className="text-sm text-muted-foreground">Businesses</p>
              <p className="text-lg font-medium tabular-nums">{businesses.length}</p>
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
            <CardTitle>Audits ({audit_summary.total})</CardTitle>
            <CardDescription>
              {audit_summary.showing < audit_summary.total
                ? `Showing the ${audit_summary.showing} most recent of ${audit_summary.total}.`
                : 'Every audit this user has run.'}{' '}
              {audit_summary.reports > 0
                ? `${audit_summary.reports} have a PDF report you can download.`
                : 'None have produced a PDF report yet.'}
            </CardDescription>
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
                    <TableHead className="text-right">Report</TableHead>
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
                      <TableCell className="text-right">
                        {audit.has_report ? (
                          <Button
                            variant="outline"
                            size="sm"
                            loading={download.isPending && download.variables?.id === audit.id}
                            onClick={() =>
                              download.mutate({
                                id: audit.id,
                                business_name: audit.business_name,
                              })
                            }
                          >
                            <Download aria-hidden="true" /> PDF
                          </Button>
                        ) : (
                          <span className="text-sm text-muted-foreground">—</span>
                        )}
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

        <ImpersonateCard userId={user.id} email={user.email} isAdmin={user.role === 'admin'} />

        <ResetPasswordCard userId={user.id} email={user.email} />
      </div>
    </>
  )
}
