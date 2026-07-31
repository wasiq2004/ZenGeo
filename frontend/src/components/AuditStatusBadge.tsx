import { CheckCircle2, Clock, Loader2, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { STATUS_LABEL, STATUS_VARIANT } from '@/lib/geo'
import type { AuditStatus } from '@/lib/types'

const ICONS = {
  pending: Clock,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
} as const

/** Status with an icon as well as a colour, so it never relies on hue alone. */
export function AuditStatusBadge({ status }: { status: AuditStatus }) {
  const Icon = ICONS[status]
  return (
    <Badge variant={STATUS_VARIANT[status]} className="gap-1">
      <Icon className={status === 'running' ? 'animate-spin' : undefined} aria-hidden="true" />
      {STATUS_LABEL[status]}
    </Badge>
  )
}
