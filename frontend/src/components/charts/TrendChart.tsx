import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface TrendPoint {
  date: string
  value: number
  label?: string
}

function ChartTooltip({
  active,
  payload,
  valueLabel,
}: {
  active?: boolean
  payload?: Array<{ payload: TrendPoint }>
  valueLabel: string
}) {
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium">{formatDate(point.date)}</p>
      <p className="text-muted-foreground">
        {valueLabel}: <span className="font-medium text-foreground">{point.value}</span>
      </p>
      {point.label && <p className="text-muted-foreground">{point.label}</p>}
    </div>
  )
}

/**
 * A single series over time.
 *
 * One series, so there is no legend box — the caption already names what is
 * plotted, and a one-swatch legend would just restate it. The final point is
 * direct-laballed; the axis and the tooltip carry the rest rather than putting
 * a number on every point. Gridlines are solid hairlines, never dashed.
 */
export function TrendChart({
  data,
  valueLabel,
  caption,
  domain,
  height = 220,
  className,
  emptyMessage = 'Not enough history yet.',
}: {
  data: TrendPoint[]
  valueLabel: string
  caption: string
  domain?: [number, number]
  height?: number
  className?: string
  emptyMessage?: string
}) {
  const [showTable, setShowTable] = useState(false)

  if (data.length === 0) {
    return <EmptyState title={emptyMessage} className={className} />
  }

  const last = data[data.length - 1]

  return (
    <figure className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between gap-4">
        <figcaption className="text-sm text-muted-foreground">{caption}</figcaption>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}
        >
          {showTable ? 'Show chart' : 'Show table'}
        </Button>
      </div>

      {showTable ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">{valueLabel}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((point, index) => (
              <TableRow key={`${point.date}-${index}`}>
                <TableCell>{formatDate(point.date)}</TableCell>
                <TableCell className="text-right tabular-nums">{point.value}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        // The container includes the x-axis band, so the card never grows a
        // nested scrollbar just to show the tick labels.
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 44, bottom: 4, left: 0 }}>
              <CartesianGrid
                stroke="var(--viz-grid)"
                strokeWidth={1}
                vertical={false}
              />
              <XAxis
                dataKey="date"
                tickFormatter={(value: string) => formatDate(value)}
                tick={{ fill: 'var(--viz-muted)', fontSize: 11 }}
                stroke="var(--viz-axis)"
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                domain={domain ?? ['auto', 'auto']}
                tick={{ fill: 'var(--viz-muted)', fontSize: 11 }}
                stroke="var(--viz-axis)"
                tickLine={false}
                axisLine={false}
                width={36}
                allowDecimals={false}
              />
              <Tooltip
                content={<ChartTooltip valueLabel={valueLabel} />}
                cursor={{ stroke: 'var(--viz-axis)', strokeWidth: 1 }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--viz-series-1)"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                /* Markers carry a surface ring so they stay legible where the
                   line crosses them, and the ring widens the hover target. */
                dot={{
                  r: 3,
                  fill: 'var(--viz-series-1)',
                  stroke: 'var(--viz-surface)',
                  strokeWidth: 2,
                }}
                activeDot={{
                  r: 5,
                  fill: 'var(--viz-series-1)',
                  stroke: 'var(--viz-surface)',
                  strokeWidth: 2,
                }}
                isAnimationActive={false}
                label={(props: { index?: number; x?: number; y?: number; value?: number }) =>
                  // Direct-label the endpoint only.
                  props.index === data.length - 1 ? (
                    <text
                      x={(props.x ?? 0) + 8}
                      y={(props.y ?? 0) + 4}
                      className="fill-foreground text-[11px] font-medium"
                    >
                      {props.value}
                    </text>
                  ) : (
                    <g />
                  )
                }
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="sr-only">
        Latest {valueLabel.toLowerCase()}: {last?.value} on {formatDate(last?.date)}.
      </p>
    </figure>
  )
}
