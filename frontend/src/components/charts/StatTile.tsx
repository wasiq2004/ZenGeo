import { ArrowDown, ArrowRight, ArrowUp } from 'lucide-react'
import type { ComponentType, ReactNode } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

/**
 * Stat tile: label, value, optional delta.
 *
 * The right form for a single headline number - a one-bar bar chart would say
 * the same thing with more ink. Values use the font's proportional figures;
 * tabular-nums is reserved for columns that must align vertically.
 */
export function StatTile({
  label,
  value,
  delta,
  deltaLabel,
  hint,
  icon: Icon,
  higherIsBetter = true,
  className,
}: {
  label: string
  value: ReactNode
  delta?: number | null
  deltaLabel?: string
  hint?: ReactNode
  icon?: ComponentType<{ className?: string }>
  higherIsBetter?: boolean
  className?: string
}) {
  const hasDelta = delta !== undefined && delta !== null && Number.isFinite(delta)
  const isFlat = hasDelta && Math.abs(delta) < 0.05
  const isGood = hasDelta && !isFlat && (delta > 0) === higherIsBetter
  const DeltaIcon = !hasDelta || isFlat ? ArrowRight : delta > 0 ? ArrowUp : ArrowDown

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardContent className="space-y-1 p-5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-muted-foreground">{label}</p>
          {Icon && <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
        </div>

        <p className="text-3xl font-semibold leading-tight tracking-tight">{value}</p>

        {hasDelta && (
          <p
            className={cn(
              'flex items-center gap-1 text-xs',
              // Direction is carried by the arrow as well as the colour, so
              // the meaning survives without colour vision.
              isFlat ? 'text-muted-foreground' : isGood ? 'text-success' : 'text-destructive',
            )}
          >
            <DeltaIcon className="size-3" aria-hidden="true" />
            <span>
              {isFlat ? 'No change' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`}
              {deltaLabel ? ` ${deltaLabel}` : ''}
            </span>
          </p>
        )}

        {hint && !hasDelta && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}
