import { Reveal } from '@/components/motion/Reveal'
import { PILLARS } from '@/lib/geo'

/**
 * Where the 100 points go.
 *
 * Horizontal bars because the pillar names are long, sorted heaviest first so
 * the eye lands on what moves the score most. One colour for every bar: the
 * pillars are nominal categories with no natural order, so shading them by
 * weight would double-encode length as hue and spend the only free channel on
 * information the bar already shows.
 *
 * The percentages are rendered as text beside each bar, not left to the visual
 * alone — the number is the point, the bar is the sense of scale.
 */
export function WeightBreakdown() {
  const ordered = [...PILLARS].sort((a, b) => b.weight - a.weight)
  const max = ordered[0]?.weight ?? 1

  return (
    <section className="border-b border-border py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-6">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,22rem)_1fr] lg:items-start">
          <Reveal>
            <h2 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">
              Where the <span className="mk-gradient-text">100 points</span> go
            </h2>
            <p className="mt-4 text-pretty text-muted-foreground">
              Not every signal matters equally. Content that an assistant can lift verbatim carries
              the most weight; a brand file it can read in one request carries the least.
            </p>
            <p className="mt-4 text-sm text-muted-foreground">
              Skip Share of Voice and its 15% is redistributed across the rest, so your score stays
              on a true 0–100 scale rather than being quietly capped at 85.
            </p>
          </Reveal>

          <Reveal delay={0.1}>
            <ul className="space-y-3.5">
              {ordered.map((pillar, i) => (
                <li key={pillar.key} className="flex items-center gap-4">
                  <span className="w-36 shrink-0 text-sm text-muted-foreground sm:w-44">
                    {pillar.shortName}
                  </span>
                  <span
                    className="h-2.5 flex-1 overflow-hidden rounded-full bg-foreground/[0.07]"
                    aria-hidden="true"
                  >
                    <span
                      className="block h-full rounded-full bg-primary transition-[width] duration-700"
                      style={{
                        width: `${(pillar.weight / max) * 100}%`,
                        transitionDelay: `${i * 60}ms`,
                      }}
                    />
                  </span>
                  <span className="mk-figure w-11 shrink-0 text-right text-sm font-semibold">
                    {Math.round(pillar.weight * 100)}%
                  </span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
