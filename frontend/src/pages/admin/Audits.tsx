import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, Skeleton } from '@/components/ui/feedback'
import { Field, Input } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/misc'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { formatDateTime, formatScore, truncate } from '@/lib/format'
import { bandBadgeVariant } from '@/lib/geo'
import type { AuditStatus, Paginated } from '@/lib/types'

interface AdminAuditRow {
  id: string
  user_id: string
  user_email: string
  business_name: string
  website_url: string
  status: AuditStatus
  geo_score: number | null
  score_band: string | null
  created_at: string
  completed_at: string | null
  error_message: string | null
}

export default function AdminAudits() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  const params = new URLSearchParams({ page: String(page), page_size: '25' })
  if (search) params.set('search', search)
  if (statusFilter !== 'all') params.set('status', statusFilter)

  const auditsQuery = useQuery({
    queryKey: ['admin-audits', page, search, statusFilter],
    queryFn: () => api.get<Paginated<AdminAuditRow>>(`/admin/audits?${params}`),
    placeholderData: (previous) => previous,
  })

  const audits = auditsQuery.data?.items ?? []
  const total = auditsQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 25))

  return (
    <>
      <PageHeader
        title="All audits"
        description={`${total} audit${total === 1 ? '' : 's'} across every account.`}
      />

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
                  placeholder="User email, business or website"
                  className="pl-9"
                />
              </div>
            )}
          </Field>
        </form>
        <div className="w-full sm:w-44">
          <Field label="Status">
            {(props) => (
              <Select
                value={statusFilter}
                onValueChange={(value) => {
                  setPage(1)
                  setStatusFilter(value)
                }}
              >
                <SelectTrigger id={props.id}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="pending">Queued</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            )}
          </Field>
        </div>
      </div>

      {auditsQuery.isLoading && audits.length === 0 ? (
        <Skeleton className="h-64 w-full" />
      ) : audits.length === 0 ? (
        <EmptyState title="No audits match that filter" />
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Business</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                  <TableHead>Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {audits.map((audit) => (
                  <TableRow key={audit.id}>
                    <TableCell>
                      <span className="block font-medium">{audit.business_name}</span>
                      <span className="block text-xs text-muted-foreground">
                        {audit.website_url}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/admin/users/${audit.user_id}`}
                        className="text-sm hover:text-primary"
                      >
                        {audit.user_email}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {audit.status === 'failed' && audit.error_message ? (
                        <Tooltip content={audit.error_message}>
                          <Badge variant="destructive">
                            failed · {truncate(audit.error_message, 24)}
                          </Badge>
                        </Tooltip>
                      ) : (
                        <Badge
                          variant={
                            audit.status === 'completed'
                              ? 'success'
                              : audit.status === 'failed'
                                ? 'destructive'
                                : 'muted'
                          }
                        >
                          {audit.status}
                        </Badge>
                      )}
                    </TableCell>
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
                      {formatDateTime(audit.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
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
    </>
  )
}
