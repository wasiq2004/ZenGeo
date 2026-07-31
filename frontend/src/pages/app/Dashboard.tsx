import { useQuery } from '@tanstack/react-query'
import { Activity, FileBarChart, Gauge, KeyRound, Sparkles, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AuditStatusBadge } from '@/components/AuditStatusBadge'
import { StatTile } from '@/components/charts/StatTile'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, Skeleton } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { formatRelative, formatScore } from '@/lib/format'
import { PILLAR_BY_KEY, PROVIDER_LABEL, bandBadgeVariant, scoreBand } from '@/lib/geo'
import type { DashboardStats } from '@/lib/types'

export default function Dashboard() {
  const { user } = useAuth()

  const statsQuery = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: () => api.get<DashboardStats>('/dashboard/stats'),
    // Keep the previous render visible while refetching - no skeleton flash.
    placeholderData: (previous) => previous,
  })

  const stats = statsQuery.data

  if (statsQuery.isLoading && !stats) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
      </>
    )
  }

  const hasAudits = (stats?.total_audits ?? 0) > 0
  const weakest = Object.entries(stats?.pillar_averages ?? {}).sort(([, a], [, b]) => a - b)[0]

  return (
    <>
      <PageHeader
        title={user?.full_name ? `Welcome back, ${user.full_name.split(' ')[0]}` : 'Dashboard'}
        description="How visible your business is inside AI answers."
        actions={
          <Button asChild>
            <Link to="/app/audits/new">
              <Sparkles aria-hidden="true" /> Run an audit
            </Link>
          </Button>
        }
      />

      {user && !user.is_email_verified && (
        <Alert variant="warning" title="Confirm your email to run audits" className="mb-6">
          <Link to="/app/settings" className="font-medium">
            Send a new confirmation link
          </Link>
        </Alert>
      )}

      {!hasAudits ? (
        <EmptyState
          icon={Gauge}
          title="No audits yet"
          description="Run your first audit to find out whether AI assistants can see, understand and cite your business."
          action={
            <Button asChild>
              <Link to="/app/audits/new">
                <Sparkles aria-hidden="true" /> Run your first audit
              </Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Latest GEO score"
              value={formatScore(stats?.latest_score)}
              delta={stats?.score_delta}
              deltaLabel="vs previous audit"
              icon={Gauge}
            />
            <StatTile
              label="Average score"
              value={formatScore(stats?.average_score)}
              hint={`Across ${stats?.completed_audits ?? 0} completed audit(s)`}
              icon={Activity}
            />
            <StatTile
              label="Best score"
              value={formatScore(stats?.best_score)}
              hint={stats?.best_score ? scoreBand(stats.best_score) : undefined}
              icon={Trophy}
            />
            <StatTile
              label="Audits run"
              value={stats?.total_audits ?? 0}
              hint={
                (stats?.running_audits ?? 0) > 0
                  ? `${stats?.running_audits} running now`
                  : 'All finished'
              }
              icon={FileBarChart}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Score over time</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendChart
                  data={(stats?.score_trend ?? []).map((point) => ({
                    date: point.date,
                    value: point.score,
                    label: point.business,
                  }))}
                  valueLabel="GEO score"
                  caption="Completed audits, oldest first."
                  domain={[0, 100]}
                  emptyMessage="Run a second audit to see your trend."
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Average by pillar</CardTitle>
                <CardDescription>
                  {weakest
                    ? `${PILLAR_BY_KEY[weakest[0]]?.name ?? weakest[0]} is holding you back most.`
                    : 'Across all your completed audits.'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {Object.entries(stats?.pillar_averages ?? {})
                    .sort(([, a], [, b]) => a - b)
                    .map(([key, value]) => (
                      <li
                        key={key}
                        className="grid grid-cols-[minmax(0,10rem)_1fr_2.5rem] items-center gap-3"
                      >
                        <span className="truncate text-sm">
                          {PILLAR_BY_KEY[key]?.shortName ?? key}
                        </span>
                        <span className="h-2.5 overflow-hidden rounded-full bg-muted">
                          <span
                            className="block h-full rounded-full"
                            style={{
                              width: `${Math.max(1, value)}%`,
                              backgroundColor: 'var(--viz-series-1)',
                            }}
                          />
                        </span>
                        <span className="text-right text-sm tabular-nums">{Math.round(value)}</span>
                      </li>
                    ))}
                </ul>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle>Recent audits</CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link to="/app/reports">View all</Link>
              </Button>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Business</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead className="text-right">When</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(stats?.recent_audits ?? []).map((audit) => (
                    <TableRow key={audit.id}>
                      <TableCell>
                        <Link
                          to={`/app/audits/${audit.id}`}
                          className="font-medium hover:text-primary"
                        >
                          {audit.business_name}
                        </Link>
                        <span className="block text-xs text-muted-foreground">
                          {audit.website_url}
                        </span>
                      </TableCell>
                      <TableCell>
                        <AuditStatusBadge status={audit.status} />
                      </TableCell>
                      <TableCell className="text-right">
                        {audit.geo_score !== null ? (
                          <Badge variant={bandBadgeVariant(audit.geo_score)}>
                            {formatScore(audit.geo_score)} · {audit.score_band}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">
                        {formatRelative(audit.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {(stats?.connected_providers.length ?? 0) === 0 ? (
            <Alert variant="info" icon={KeyRound} title="Share of Voice is locked">
              Connect an OpenAI, Anthropic or Perplexity key to test your own prompts against real
              assistants.{' '}
              <Link to="/app/settings?tab=keys" className="font-medium">
                Connect a key
              </Link>
            </Alert>
          ) : (
            <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              Testing against:
              {stats?.connected_providers.map((provider) => (
                <Badge key={provider} variant="secondary">
                  {PROVIDER_LABEL[provider] ?? provider}
                </Badge>
              ))}
            </p>
          )}
        </div>
      )}
    </>
  )
}
