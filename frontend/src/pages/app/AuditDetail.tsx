import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  Quote,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AuditStatusBadge } from '@/components/AuditStatusBadge'
import { PillarBars } from '@/components/charts/PillarBars'
import { ScoreMeter } from '@/components/charts/ScoreMeter'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, LoadingScreen, Skeleton } from '@/components/ui/feedback'
import { Progress, Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from '@/components/ui/misc'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/components/ui/toast'
import { api, apiDownload } from '@/lib/api'
import { formatDateTime, formatDuration, formatPercent, formatTime, truncate } from '@/lib/format'
import { EFFORT_LABEL, EFFORT_ORDER, IMPACT_VARIANT, PROVIDER_LABEL } from '@/lib/geo'
import type { AuditDetail as AuditDetailType, PillarResult, Recommendation } from '@/lib/types'

export default function AuditDetail() {
  const { auditId } = useParams<{ auditId: string }>()
  const { toast } = useToast()

  const auditQuery = useQuery({
    queryKey: ['audit', auditId],
    queryFn: () => api.get<AuditDetailType>(`/audits/${auditId}`),
    // Poll while the worker is still going, then stop.
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 2500 : false
    },
  })

  const download = useMutation({
    mutationFn: async () => {
      const blob = await apiDownload(`/reports/${auditId}`)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `checkgeo-${auditId?.slice(0, 8)}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: () => toast({ title: 'Could not download the report', variant: 'error' }),
  })

  if (auditQuery.isLoading) return <LoadingScreen label="Loading your audit" />

  if (auditQuery.isError || !auditQuery.data) {
    return (
      <>
        <PageHeader title="Audit" />
        <Alert variant="error" title="We could not load this audit">
          It may have been deleted, or it belongs to another account.
        </Alert>
      </>
    )
  }

  const audit = auditQuery.data
  const isRunning = audit.status === 'pending' || audit.status === 'running'

  return (
    <>
      <PageHeader
        title={audit.business_name || 'Audit'}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <a
              href={audit.website_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 hover:text-foreground"
            >
              {audit.website_url}
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>
            <span aria-hidden="true">·</span>
            <AuditStatusBadge status={audit.status} />
            <span aria-hidden="true">·</span>
            <span>{formatDateTime(audit.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm">
              <Link to="/app/reports">
                <ArrowLeft aria-hidden="true" /> All reports
              </Link>
            </Button>
            {audit.has_report && (
              <Button size="sm" loading={download.isPending} onClick={() => download.mutate()}>
                <Download aria-hidden="true" /> Download PDF
              </Button>
            )}
          </>
        }
      />

      {audit.status === 'failed' && (
        <Alert variant="error" title="This audit did not finish" className="mb-6">
          {audit.error_message ?? 'Something went wrong. Try running it again.'}
        </Alert>
      )}

      {isRunning ? (
        <RunningView audit={audit} />
      ) : audit.status === 'completed' ? (
        <ResultsView audit={audit} />
      ) : (
        <EmptyState
          title="No results"
          description="This audit stopped before it produced a score."
          action={
            <Button asChild>
              <Link to="/app/audits/new">Run a new audit</Link>
            </Button>
          }
        />
      )}
    </>
  )
}

function RunningView({ audit }: { audit: AuditDetailType }) {
  const events = [...audit.events].reverse()

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center gap-3">
            <Loader2 className="size-5 animate-spin text-primary" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">
                {audit.status === 'pending' ? 'Queued…' : 'Running your audit…'}
              </p>
              <p className="text-sm text-muted-foreground">
                {events[0]?.message ?? 'Getting started.'}
              </p>
            </div>
            <span className="text-2xl font-semibold tabular-nums">
              {Math.round(audit.progress)}%
            </span>
          </div>
          <Progress value={audit.progress} aria-label="Audit progress" />
          <p className="text-xs text-muted-foreground">
            You can leave this page — we will email you when it is done if notifications are on.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Live progress</CardTitle>
          <CardDescription>Every stage, as it happens.</CardDescription>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <ol className="space-y-2.5">
              {events.map((event) => (
                <li key={event.id} className="flex gap-3 text-sm">
                  <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                    {formatTime(event.created_at)}
                  </span>
                  <span
                    className={
                      event.level === 'error'
                        ? 'text-destructive'
                        : event.level === 'warning'
                          ? 'text-warning'
                          : ''
                    }
                  >
                    {event.message}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function ResultsView({ audit }: { audit: AuditDetailType }) {
  const pillars: PillarResult[] = Object.values(audit.pillar_scores ?? {})
  const recommendations = audit.recommendations ?? []
  const sov = audit.share_of_voice_results
  const skipped = pillars.filter((p) => p.skipped)

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[auto,1fr]">
        <Card className="flex items-center justify-center p-6">
          <ScoreMeter score={audit.geo_score} />
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pillar breakdown</CardTitle>
            <CardDescription>
              Finished in {formatDuration(audit.started_at, audit.completed_at)}.
              {skipped.length > 0 &&
                ' One pillar was not tested, so its weight was shared across the rest.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PillarBars pillars={pillars} />
          </CardContent>
        </Card>
      </div>

      {skipped.map((pillar) => (
        <Alert key={pillar.key} variant="info" title={`${pillar.name} was not tested`}>
          {pillar.skip_reason}{' '}
          <Link to="/app/settings?tab=keys" className="font-medium">
            Connect an API key
          </Link>{' '}
          to unlock it.
        </Alert>
      ))}

      <Tabs defaultValue="recommendations">
        <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
          <TabsTrigger value="recommendations">
            Fixes ({recommendations.length})
          </TabsTrigger>
          <TabsTrigger value="pillars">Pillar detail</TabsTrigger>
          <TabsTrigger value="sov">Share of Voice</TabsTrigger>
        </TabsList>

        <TabsContent value="recommendations">
          <RecommendationList recommendations={recommendations} />
        </TabsContent>

        <TabsContent value="pillars">
          <div className="space-y-4">
            {pillars.map((pillar) => (
              <PillarCard key={pillar.key} pillar={pillar} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="sov">
          <ShareOfVoiceView data={sov} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function RecommendationList({ recommendations }: { recommendations: Recommendation[] }) {
  if (recommendations.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Nothing to fix"
        description="Every check passed. Re-run this audit after your next big content change."
      />
    )
  }

  return (
    <div className="space-y-6">
      {EFFORT_ORDER.map((effort) => {
        const group = recommendations.filter((rec) => rec.effort === effort)
        if (group.length === 0) return null
        return (
          <section key={effort} className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">
              {EFFORT_LABEL[effort]} ({group.length})
            </h2>
            {group.map((rec) => (
              <Card key={rec.id}>
                <CardContent className="space-y-2 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="font-medium leading-snug">{rec.title}</h3>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Badge variant={IMPACT_VARIANT[rec.impact]}>{rec.impact} impact</Badge>
                      {!rec.actionable && (
                        <Tooltip content="You said you cannot add files to the site root — someone with that access needs to action this.">
                          <Badge variant="outline">Needs site access</Badge>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {rec.detail}
                  </p>
                </CardContent>
              </Card>
            ))}
          </section>
        )
      })}
    </div>
  )
}

function PillarCard({ pillar }: { pillar: PillarResult }) {
  const [open, setOpen] = useState(false)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <CardTitle>{pillar.name}</CardTitle>
            <CardDescription>{pillar.summary}</CardDescription>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-2xl font-semibold tabular-nums">
              {pillar.skipped ? '—' : Math.round(pillar.score)}
            </p>
            <p className="text-xs text-muted-foreground">
              {pillar.skipped
                ? 'not tested'
                : `${Math.round(pillar.effective_weight * 100)}% of score`}
            </p>
          </div>
        </div>
      </CardHeader>
      {pillar.checks.length > 0 && (
        <CardContent>
          <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? 'Hide' : 'Show'} {pillar.checks.length} check
            {pillar.checks.length === 1 ? '' : 's'}
          </Button>
          {open && (
            <ul className="mt-3 space-y-3">
              {pillar.checks.map((check, index) => (
                <li key={index} className="flex gap-3 text-sm">
                  <span className="mt-0.5 shrink-0">
                    {check.passed === null ? (
                      <span className="text-muted-foreground" aria-label="Note">
                        ·
                      </span>
                    ) : check.passed ? (
                      <CheckCircle2 className="size-4 text-success" aria-label="Passed" />
                    ) : (
                      <XCircle className="size-4 text-destructive" aria-label="Failed" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{check.label}</span>
                    {check.max_points > 0 && (
                      <span className="ml-2 text-xs tabular-nums text-muted-foreground">
                        {check.points}/{check.max_points}
                      </span>
                    )}
                    <span className="block text-muted-foreground">{check.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      )}
    </Card>
  )
}

function ShareOfVoiceView({ data }: { data: AuditDetailType['share_of_voice_results'] }) {
  if (!data || !data.tested) {
    return (
      <EmptyState
        icon={Globe}
        title="Share of Voice was not tested"
        description={
          data?.skip_reason ??
          'Connect an AI provider key and add target prompts to unlock live testing.'
        }
        action={
          <Button asChild>
            <Link to="/app/settings?tab=keys">Connect a key</Link>
          </Button>
        }
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">Mention rate</p>
            <p className="text-3xl font-semibold">{formatPercent(data.mention_rate)}</p>
            <p className="text-xs text-muted-foreground">Answers that named you at all</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">Citation rate</p>
            <p className="text-3xl font-semibold">{formatPercent(data.citation_rate)}</p>
            <p className="text-xs text-muted-foreground">Answers that linked to your domain</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">Calls made</p>
            <p className="text-3xl font-semibold tabular-nums">{data.total_calls}</p>
            <p className="text-xs text-muted-foreground">
              {data.prompts_tested} prompt{data.prompts_tested === 1 ? '' : 's'} ×{' '}
              {data.providers_tested.length} provider
              {data.providers_tested.length === 1 ? '' : 's'}
              {data.failed_calls > 0 && ` · ${data.failed_calls} failed`}
            </p>
          </CardContent>
        </Card>
      </div>

      {Object.keys(data.competitor_share ?? {}).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Competitors in the same answers</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {Object.entries(data.competitor_share)
              .sort(([, a], [, b]) => b - a)
              .map(([name, count]) => (
                <Badge key={name} variant="secondary">
                  {name} · {count}
                </Badge>
              ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Every prompt tested</CardTitle>
          <CardDescription>
            Tone is a keyword heuristic over the sentences that name you, not a model judgement.
            Citation rates compare fairly only between web-grounded providers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Prompt</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Mentioned</TableHead>
                <TableHead>Cited</TableHead>
                <TableHead>What it said</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.results.map((row, index) => (
                <TableRow key={index}>
                  <TableCell className="max-w-[16rem] align-top text-sm">{row.prompt}</TableCell>
                  <TableCell className="align-top text-sm">
                    {PROVIDER_LABEL[row.provider] ?? row.provider}
                    <span className="block text-xs text-muted-foreground">{row.model}</span>
                  </TableCell>
                  <TableCell className="align-top">
                    {row.error ? (
                      <Badge variant="muted">Error</Badge>
                    ) : row.mentioned ? (
                      <Badge variant="success" className="gap-1">
                        <CheckCircle2 aria-hidden="true" /> Yes
                        {row.position ? ` · #${row.position}` : ''}
                      </Badge>
                    ) : (
                      <Badge variant="muted">No</Badge>
                    )}
                  </TableCell>
                  <TableCell className="align-top">
                    {row.cited ? (
                      <Badge variant="success">Yes</Badge>
                    ) : (
                      <Badge variant="muted">No</Badge>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[24rem] align-top text-sm text-muted-foreground">
                    {row.error ? (
                      <span className="italic">{row.error}</span>
                    ) : (
                      <>
                        <span className="flex gap-1.5">
                          <Quote className="mt-1 size-3 shrink-0" aria-hidden="true" />
                          <span>{truncate(row.excerpt, 220)}</span>
                        </span>
                        <span className="mt-1 flex flex-wrap items-center gap-1.5">
                          {row.sentiment && (
                            <Badge variant="outline" className="text-[10px]">
                              {row.sentiment}
                            </Badge>
                          )}
                          {row.competitors_mentioned.map((name) => (
                            <Badge key={name} variant="muted" className="text-[10px]">
                              {name}
                            </Badge>
                          ))}
                        </span>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
