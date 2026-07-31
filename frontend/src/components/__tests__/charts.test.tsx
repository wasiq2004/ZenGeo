import { describe, expect, it } from 'vitest'
import { PillarBars } from '@/components/charts/PillarBars'
import { ScoreMeter } from '@/components/charts/ScoreMeter'
import { StatTile } from '@/components/charts/StatTile'
import { PILLARS, scoreBand } from '@/lib/geo'
import type { PillarResult } from '@/lib/types'
import { render, screen, userEvent, within } from '@/test/utils'

function pillar(key: string, score: number, skipped = false): PillarResult {
  const meta = PILLARS.find((p) => p.key === key)!
  return {
    key,
    name: meta.name,
    score,
    weight: meta.weight,
    effective_weight: skipped ? 0 : meta.weight,
    skipped,
    skip_reason: skipped ? 'No API key connected.' : null,
    summary: 'Summary text.',
    checks: [],
  }
}

describe('ScoreMeter', () => {
  it('shows the number and its band label together', () => {
    render(<ScoreMeter score={72} />)

    expect(screen.getByText('72')).toBeInTheDocument()
    // The band label is what keeps the status colour from carrying the
    // meaning alone.
    expect(screen.getByText('Good')).toBeInTheDocument()
  })

  it('describes itself to assistive technology', () => {
    render(<ScoreMeter score={35} />)

    expect(screen.getByRole('img')).toHaveAccessibleName(
      /35 out of 100, band Poor/i,
    )
  })

  it('renders a placeholder rather than a zero when there is no score', () => {
    render(<ScoreMeter score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it.each([
    [12, 'Poor'],
    [45, 'Needs Work'],
    [65, 'Good'],
    [91, 'Excellent'],
  ])('labels %i as %s', (score, band) => {
    render(<ScoreMeter score={score} />)
    expect(screen.getByText(band)).toBeInTheDocument()
    expect(scoreBand(score)).toBe(band)
  })
})

describe('PillarBars', () => {
  const pillars = [
    pillar('crawlability', 80),
    pillar('llms_txt', 10),
    pillar('extractability', 45),
  ]

  it('direct-labels every bar so no value is tooltip-only', () => {
    render(<PillarBars pillars={pillars} />)

    expect(screen.getByText('80')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('45')).toBeInTheDocument()
  })

  it('orders the weakest pillar first', () => {
    render(<PillarBars pillars={pillars} />)

    const items = screen.getAllByRole('listitem')
    expect(within(items[0]!).getByText('10')).toBeInTheDocument()
  })

  it('offers a table view of the same numbers', async () => {
    render(<PillarBars pillars={pillars} />)

    await userEvent.click(screen.getByRole('button', { name: /show table/i }))

    const table = screen.getByRole('table')
    expect(within(table).getByText('llms.txt Brand File')).toBeInTheDocument()
    expect(within(table).getByText('10')).toBeInTheDocument()
  })

  it('marks a skipped pillar as not tested rather than as zero', () => {
    render(<PillarBars pillars={[...pillars, pillar('share_of_voice', 0, true)]} />)

    expect(screen.getByText('Not tested')).toBeInTheDocument()
  })
})

describe('StatTile', () => {
  it('renders label and value', () => {
    render(<StatTile label="Average score" value={64} />)

    expect(screen.getByText('Average score')).toBeInTheDocument()
    expect(screen.getByText('64')).toBeInTheDocument()
  })

  it('signs the delta and states what it compares against', () => {
    render(<StatTile label="Latest" value={70} delta={5.4} deltaLabel="vs previous audit" />)

    expect(screen.getByText(/\+5\.4 vs previous audit/)).toBeInTheDocument()
  })

  it('says "no change" rather than showing a signed zero', () => {
    render(<StatTile label="Latest" value={70} delta={0} />)

    expect(screen.getByText(/no change/i)).toBeInTheDocument()
  })

  it('treats a fall as good when lower is better', () => {
    const { container } = render(
      <StatTile label="Failures" value={2} delta={-3} higherIsBetter={false} />,
    )

    expect(container.querySelector('.text-success')).not.toBeNull()
  })
})
