import { useQuery } from '@tanstack/react-query'
import { ScrollText } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/AppShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, Skeleton } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { AdminLogEntry, Paginated } from '@/lib/types'

const ACTION_LABEL: Record<string, string> = {
  'user.update': 'Changed a user',
  'user.force_logout': 'Revoked sessions',
}

function describeChange(metadata: Record<string, unknown>): string {
  const parts: string[] = []
  for (const [field, change] of Object.entries(metadata)) {
    if (change && typeof change === 'object' && 'from' in change && 'to' in change) {
      const { from, to } = change as { from: unknown; to: unknown }
      parts.push(`${field}: ${String(from)} → ${String(to)}`)
    } else {
      parts.push(`${field}: ${String(change)}`)
    }
  }
  return parts.join(' · ')
}

export default function AdminActivity() {
  const [page, setPage] = useState(1)

  const logQuery = useQuery({
    queryKey: ['admin-activity', page],
    queryFn: () => api.get<Paginated<AdminLogEntry>>(`/admin/activity?page=${page}&page_size=25`),
    placeholderData: (previous) => previous,
  })

  const entries = logQuery.data?.items ?? []
  const total = logQuery.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / 25))

  return (
    <>
      <PageHeader
        title="Activity log"
        description="Every state-changing admin action. Append-only — nothing in the app can edit or remove an entry."
      />

      {logQuery.isLoading && entries.length === 0 ? (
        <Skeleton className="h-64 w-full" />
      ) : entries.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="Nothing recorded yet"
          description="Admin actions such as changing a role or disabling an account will appear here."
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Administrator</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Detail</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {formatDateTime(entry.created_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {ACTION_LABEL[entry.action] ?? entry.action}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">{entry.admin_email ?? '—'}</TableCell>
                    <TableCell className="text-sm">
                      {entry.target_user_id ? (
                        <Link
                          to={`/admin/users/${entry.target_user_id}`}
                          className="hover:text-primary"
                        >
                          {entry.target_user_email ?? entry.target_user_id}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {Object.keys(entry.metadata).length > 0 && (
                        <span className="block">{describeChange(entry.metadata)}</span>
                      )}
                      {entry.reason && <span className="block italic">{entry.reason}</span>}
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
            Page {page} of {totalPages} · {total} entries
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
