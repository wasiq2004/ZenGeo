import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PILLAR_BY_KEY } from '@/lib/geo'
import type { PillarResult } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Pillar comparison.
 *
 * Horizontal bars, because the job is "compare magnitude across seven
 * long-named categories". Every bar is the SAME hue: the pillars are nominal
 * categories, so colouring each one by its own score would double-encode bar
 * length as hue — the value is already the bar's length. Each bar is
 * direct-labelled, and a table view carries the same numbers for anyone who
 * cannot use the chart.
 */
export function PillarBars({
  pillars,
  className,
}: {
  pillars: PillarResult[]
  className?: string
}) {
  const [showTable, setShowTable] = useState(false)

  // Worst first: the reader is here to find what to fix.
  const ordered = [...pillars].sort((a, b) => {
    if (a.skipped !== b.skipped) return a.skipped ? 1 : -1
    return a.score - b.score
  })

  return (
    <figure className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between gap-4">
        <figcaption className="text-sm text-muted-foreground">
          Each pillar scored 0–100, weakest first.
        </figcaption>
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
              <TableHead>Pillar</TableHead>
              <TableHead className="text-right">Weight</TableHead>
              <TableHead className="text-right">Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordered.map((pillar) => (
              <TableRow key={pillar.key}>
                <TableCell className="font-medium">{pillar.name}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {pillar.skipped ? '—' : `${Math.round(pillar.effective_weight * 100)}%`}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {pillar.skipped ? 'Not tested' : Math.round(pillar.score)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <ul className="space-y-3">
          {ordered.map((pillar) => {
            const meta = PILLAR_BY_KEY[pillar.key]
            return (
              <li key={pillar.key} className="grid grid-cols-[minmax(0,11rem)_1fr_2.5rem] items-center gap-3">
                <span className="truncate text-sm" title={pillar.name}>
                  {meta?.shortName ?? pillar.name}
                </span>

                {pillar.skipped ? (
                  <span className="text-xs italic text-muted-foreground">Not tested</span>
                ) : (
                  <span
                    className="h-2.5 w-full overflow-hidden rounded-full bg-muted"
                    role="img"
                    aria-label={`${pillar.name}: ${Math.round(pillar.score)} out of 100`}
                  >
                    <span
                      className="block h-full rounded-full transition-[width] duration-700"
                      style={{
                        width: `${Math.max(1, pillar.score)}%`,
                        backgroundColor: 'var(--viz-series-1)',
                      }}
                    />
                  </span>
                )}

                {/* Direct label at the bar's tip - the value is never tooltip-only. */}
                <span className="text-right text-sm font-medium tabular-nums">
                  {pillar.skipped ? '—' : Math.round(pillar.score)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </figure>
  )
}
