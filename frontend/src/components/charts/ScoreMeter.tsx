import { cn } from '@/lib/utils'
import { bandColor, scoreBand } from '@/lib/geo'

/**
 * The single headline number, drawn as a meter.
 *
 * A score against a fixed limit is a meter, not a chart: the fill carries
 * severity and the unfilled track is a recessive step of the same surface. The
 * band label is always rendered beside the number, so the status colour never
 * has to carry the meaning by itself.
 */
export function ScoreMeter({
  score,
  size = 200,
  label = 'GEO score',
  className,
}: {
  score: number | null
  size?: number
  label?: string
  className?: string
}) {
  const value = score ?? 0
  const band = scoreBand(score)
  const colour = bandColor(score)

  const stroke = Math.max(10, Math.round(size * 0.075))
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  // Three-quarter arc: leaves a visual "base" so the meter reads as a gauge.
  const arcPortion = 0.75
  const arcLength = circumference * arcPortion
  const filled = arcLength * Math.max(0, Math.min(100, value)) / 100

  return (
    <figure className={cn('flex flex-col items-center gap-2', className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={`${label}: ${value.toFixed(0)} out of 100, band ${band}`}
          /* Rotated so the arc gap sits at the bottom. */
          style={{ transform: 'rotate(135deg)' }}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--viz-grid)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${arcLength} ${circumference}`}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={colour}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${filled} ${circumference}`}
            style={{ transition: 'stroke-dasharray 700ms ease-out' }}
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {/* Hero figure: proportional digits, same sans as everything else. */}
          <span
            className="font-semibold leading-none tracking-tight"
            style={{ fontSize: size * 0.28 }}
          >
            {score === null ? '—' : value.toFixed(0)}
          </span>
          <span className="mt-1 text-xs text-muted-foreground">out of 100</span>
        </div>
      </div>

      <figcaption className="flex flex-col items-center gap-1">
        {/* The label is what makes the status colour legible to everyone. */}
        <span
          className="rounded-full px-3 py-1 text-sm font-medium text-white"
          style={{ backgroundColor: colour }}
        >
          {band}
        </span>
        <span className="text-xs text-muted-foreground">{label}</span>
      </figcaption>
    </figure>
  )
}
