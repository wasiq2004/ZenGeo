import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, ClipboardList, Gauge, Users } from 'lucide-react'
import { StatTile } from '@/components/charts/StatTile'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, Skeleton } from '@/components/ui/feedback'
import { api } from '@/lib/api'
import { formatScore } from '@/lib/format'
import { PROVIDER_LABEL } from '@/lib/geo'
import type { AdminStats } from '@/lib/types'

export default function AdminOverview() {
  const statsQuery = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => api.get<AdminStats>('/admin/stats'),
    // Hold the previous render while refetching - no skeleton flash.
    placeholderData: (previous) => previous,
  })

  const stats = statsQuery.data

  if (statsQuery.isLoading && !stats) {
    return (
      <>
        <PageHeader title="Platform overview" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
      </>
    )
  }

  const providerTotal = Object.values(stats?.provider_usage ?? {}).reduce((a, b) => a + b, 0)

  return (
    <>
      <PageHeader title="Platform overview" description="How the whole installation is doing." />

      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Total users"
            value={stats?.total_users ?? 0}
            hint={`${stats?.new_users_7d ?? 0} new this week`}
            icon={Users}
          />
          <StatTile
            label="Active in last 30 days"
            value={stats?.active_users_30d ?? 0}
            hint="Signed in at least once"
            icon={Activity}
          />
          <StatTile
            label="Audits run"
            value={stats?.total_audits ?? 0}
            hint={`${stats?.audits_today ?? 0} today · ${stats?.audits_7d ?? 0} this week`}
            icon={ClipboardList}
          />
          <StatTile
            label="Average GEO score"
            value={formatScore(stats?.average_geo_score)}
            hint="Across every completed audit"
            icon={Gauge}
          />
        </div>

        {((stats?.running_audits ?? 0) > 0 || (stats?.failed_audits_7d ?? 0) > 0) && (
          <div className="grid gap-4 sm:grid-cols-2">
            {(stats?.running_audits ?? 0) > 0 && (
              <Alert variant="info" title={`${stats?.running_audits} audit(s) running now`}>
                The worker is processing these.
              </Alert>
            )}
            {(stats?.failed_audits_7d ?? 0) > 0 && (
              <Alert
                variant="warning"
                icon={AlertTriangle}
                title={`${stats?.failed_audits_7d} audit(s) failed this week`}
              >
                The audits table carries each error message.
              </Alert>
            )}
          </div>
        )}

        {/*
          Two separate single-series charts rather than one dual-axis plot.
          Signups and audits differ by an order of magnitude, and overlaying
          them on two y-scales would invent a correlation that is not there.
        */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Signups</CardTitle>
              <CardDescription>New accounts per day.</CardDescription>
            </CardHeader>
            <CardContent>
              <TrendChart
                data={(stats?.signups_trend ?? []).map((point) => ({
                  date: point.date,
                  value: point.count,
                }))}
                valueLabel="Signups"
                caption="Last 30 days."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Audits</CardTitle>
              <CardDescription>Audits started per day.</CardDescription>
            </CardHeader>
            <CardContent>
              <TrendChart
                data={(stats?.audits_trend ?? []).map((point) => ({
                  date: point.date,
                  value: point.count,
                }))}
                valueLabel="Audits"
                caption="Last 30 days."
              />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Connected AI providers</CardTitle>
            <CardDescription>Active keys by provider, across all users.</CardDescription>
          </CardHeader>
          <CardContent>
            {providerTotal === 0 ? (
              <p className="text-sm text-muted-foreground">No keys connected yet.</p>
            ) : (
              <ul className="space-y-3">
                {Object.entries(stats?.provider_usage ?? {})
                  .sort(([, a], [, b]) => b - a)
                  .map(([provider, count]) => (
                    <li
                      key={provider}
                      className="grid grid-cols-[minmax(0,11rem)_1fr_3rem] items-center gap-3"
                    >
                      <span className="truncate text-sm">
                        {PROVIDER_LABEL[provider] ?? provider}
                      </span>
                      <span className="h-2.5 overflow-hidden rounded-full bg-muted">
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: `${(count / providerTotal) * 100}%`,
                            backgroundColor: 'var(--viz-series-1)',
                          }}
                        />
                      </span>
                      <span className="text-right text-sm tabular-nums">{count}</span>
                    </li>
                  ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">Privacy</Badge>
          <span>
            Administrators can see that a user has connected a key and which provider it is for.
            The key itself is encrypted at rest and no endpoint returns it — not even here.
          </span>
        </p>
      </div>
    </>
  )
}
