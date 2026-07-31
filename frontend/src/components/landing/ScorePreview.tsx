/**
 * The animated product mock in the hero.
 *
 * Sample data, clearly labelled as such - it is an illustration of the report,
 * not a live audit.
 *
 * Encoding follows the same rules as the real report, so the marketing page
 * does not promise a chart the product does not draw:
 *   * the composite score is a meter - one value against a fixed 0-100 limit -
 *     and carries the only status colour on the panel, always beside its band
 *     name in text, so colour never carries the meaning alone;
 *   * the pillars are nominal categories, so they share ONE hue and are each
 *     direct-labelled with their number. Colouring them by band would imply an
 *     ordering the category axis does not have.
 */
import { motion, useReducedMotion } from 'motion/react'
import { CountUp } from '@/components/motion/CountUp'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'

const SAMPLE_SCORE = 57

const SAMPLE_PILLARS = [
  { label: 'Crawlability', value: 88 },
  { label: 'llms.txt', value: 20 },
  { label: 'Schema', value: 64 },
  { label: 'Extractability', value: 72 },
  { label: 'Evidence', value: 45 },
  { label: 'Authority', value: 58 },
  { label: 'Share of Voice', value: 33 },
]

const RADIUS = 52
const EASE = [0.22, 1, 0.36, 1] as const

function Gauge({ score }: { score: number }) {
  const reduced = useReducedMotion()
  const fraction = score / 100

  return (
    <div className="flex flex-col items-center justify-center gap-1 sm:border-r sm:border-border sm:pr-8">
      <div className="relative">
        <svg viewBox="0 0 120 120" className="size-32 -rotate-90" aria-hidden="true">
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke="hsl(var(--muted))"
            strokeWidth="10"
          />
          {/* pathLength normalises the arc to 0-1, so the fraction is the value. */}
          <motion.circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            stroke="var(--band-fair)"
            strokeWidth="10"
            strokeLinecap="round"
            initial={{ pathLength: reduced ? fraction : 0 }}
            whileInView={{ pathLength: fraction }}
            // Low threshold on purpose: the panel sits at the fold, and a
            // visitor who never scrolls should still see it fill rather than
            // stare at an empty ring.
            viewport={{ once: true, amount: 0.2 }}
            transition={reduced ? { duration: 0 } : { duration: 1.5, ease: EASE }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <CountUp to={score} className="text-3xl font-semibold tabular-nums" />
          <span className="text-[11px] text-muted-foreground">/ 100</span>
        </div>
      </div>
      {/* The band in words - the arc colour is a reinforcement, not the message. */}
      <Badge variant="warning" className="mt-2">
        Needs Work
      </Badge>
      <span className="sr-only">Composite GEO score {score} out of 100, band: Needs Work.</span>
    </div>
  )
}

function PillarRow({ label, value, index }: { label: string; value: number; index: number }) {
  const reduced = useReducedMotion()

  return (
    <li className="grid grid-cols-[7.5rem,1fr,2.5rem] items-center gap-3">
      <span className="truncate text-xs text-muted-foreground">{label}</span>
      <span className="h-1.5 overflow-hidden rounded-full bg-muted">
        {/* scaleX rather than width: transform animates on the compositor, so a
            row of seven bars does not trigger seven layout passes per frame. */}
        <motion.span
          className="block h-full origin-left rounded-full"
          style={{ width: `${value}%`, backgroundColor: 'var(--viz-series-1)' }}
          initial={{ scaleX: reduced ? 1 : 0 }}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={
            reduced ? { duration: 0 } : { duration: 0.7, delay: 0.15 + index * 0.07, ease: EASE }
          }
        />
      </span>
      <span className="text-right text-xs tabular-nums text-muted-foreground">{value}</span>
    </li>
  )
}

export function ScorePreview() {
  return (
    <Card className="overflow-hidden shadow-xl">
      <div className="flex items-center gap-1.5 border-b border-border bg-muted/40 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-destructive/60" />
        <span className="size-2.5 rounded-full bg-warning/60" />
        <span className="size-2.5 rounded-full bg-success/60" />
        <span className="ml-3 text-xs text-muted-foreground">Example report</span>
      </div>
      <CardContent className="grid gap-8 p-6 sm:grid-cols-[auto,1fr] sm:p-8">
        <Gauge score={SAMPLE_SCORE} />
        <ul className="space-y-2.5">
          {SAMPLE_PILLARS.map((pillar, index) => (
            <PillarRow key={pillar.label} index={index} {...pillar} />
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

/** Headline numbers under the hero mock. */
export function PreviewStats() {
  const stats = [
    { value: 7, label: 'weighted pillars', suffix: '' },
    { value: 100, label: 'point scale', suffix: '' },
    { value: 0, label: 'cost to run', prefix: '$' },
  ]

  return (
    <dl className="mt-10 grid grid-cols-3 gap-4 border-t border-border pt-8">
      {stats.map((stat) => (
        <div key={stat.label} className="text-center">
          <dt className="sr-only">{stat.label}</dt>
          <dd>
            <CountUp
              to={stat.value}
              prefix={stat.prefix ?? ''}
              className="block text-2xl font-semibold tabular-nums sm:text-3xl"
            />
            <span className="mt-1 block text-xs text-muted-foreground">{stat.label}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
}
