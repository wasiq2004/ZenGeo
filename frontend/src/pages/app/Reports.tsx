import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileBarChart, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AuditStatusBadge } from '@/components/AuditStatusBadge'
import { TrendChart } from '@/components/charts/TrendChart'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/dialog'
import { EmptyState, Skeleton } from '@/components/ui/feedback'
import { Tooltip } from '@/components/ui/misc'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useToast } from '@/components/ui/toast'
import { api, apiDownload } from '@/lib/api'
import { formatDateTime, formatScore } from '@/lib/format'
import { bandBadgeVariant } from '@/lib/geo'
import type { AuditSummary, Paginated } from '@/lib/types'

export default function Reports() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [page, setPage] = useState(1)
  const [pendingDelete, setPendingDelete] = useState<AuditSummary | null>(null)

  const auditsQuery = useQuery({
    queryKey: ['audits', page],
    queryFn: () => api.get<Paginated<AuditSummary>>(`/audits?page=${page}&page_size=25`),
    placeholderData: (previous) => previous,
  })

  const download = useMutation({
    mutationFn: async (audit: AuditSummary) => {
      const blob = await apiDownload(`/reports/${audit.id}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `checkgeo-${audit.business_name.replace(/\W+/g, '-').toLowerCase()}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: () => toast({ title: 'Could not download that report', variant: 'error' }),
  })

  const remove = useMutation({
    mutationFn: (audit: AuditSummary) => api.delete(`/audits/${audit.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['audits'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard-stats'] })
      setPendingDelete(null)
      toast({ title: 'Audit deleted' })
    },
    onError: (error) =>
      toast({
        title: 'Could not delete that audit',
        description: error instanceof Error ? error.message : undefined,
        variant: 'error',
      }),
  })

  const audits = auditsQuery.data?.items ?? []
  const total = auditsQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 25))

  const completed = [...audits]
    .filter((audit) => audit.status === 'completed' && audit.geo_score !== null)
    .reverse()

  return (
    <>
      <PageHeader
        title="Reports"
        description="Every audit you have run, with its PDF."
        actions={
          <Button asChild>
            <Link to="/app/audits/new">
              <Sparkles aria-hidden="true" /> Run an audit
            </Link>
          </Button>
        }
      />

      {auditsQuery.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : audits.length === 0 ? (
        <EmptyState
          icon={FileBarChart}
          title="No reports yet"
          description="Once you run an audit, its report shows up here and stays downloadable."
          action={
            <Button asChild>
              <Link to="/app/audits/new">Run your first audit</Link>
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {completed.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Score over time</CardTitle>
              </CardHeader>
              <CardContent>
                <TrendChart
                  data={completed.map((audit) => ({
                    date: audit.completed_at ?? audit.created_at,
                    value: Math.round(audit.geo_score ?? 0),
                    label: audit.business_name,
                  }))}
                  valueLabel="GEO score"
                  caption="Completed audits on this page, oldest first."
                  domain={[0, 100]}
                />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="p-0">
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
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDateTime(audit.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          {audit.has_report && (
                            <Tooltip content="Download the PDF report">
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                loading={
                                  download.isPending && download.variables?.id === audit.id
                                }
                                onClick={() => download.mutate(audit)}
                                aria-label={`Download the report for ${audit.business_name}`}
                              >
                                <Download aria-hidden="true" />
                              </Button>
                            </Tooltip>
                          )}
                          <Tooltip content="Delete this audit">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="text-destructive hover:bg-destructive/10"
                              onClick={() => setPendingDelete(audit)}
                              aria-label={`Delete the audit for ${audit.business_name}`}
                            >
                              <Trash2 aria-hidden="true" />
                            </Button>
                          </Tooltip>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Page {page} of {totalPages} · {total} audit{total === 1 ? '' : 's'}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
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
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete this audit?"
        description={
          <>
            The audit for{' '}
            <span className="font-medium text-foreground">{pendingDelete?.business_name}</span> and
            its PDF report will be removed permanently.
          </>
        }
        confirmLabel="Delete audit"
        destructive
        loading={remove.isPending}
        onConfirm={() => pendingDelete && remove.mutate(pendingDelete)}
      />
    </>
  )
}
