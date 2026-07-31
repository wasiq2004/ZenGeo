/**
 * Infinite strip of the assistants an audit is scored against. Pauses on hover
 * (and on keyboard focus, so a keyboard user can also stop it to read).
 *
 * These are plain wordmarks, not the vendors' logo files: naming the assistants
 * we actually query is factual, but shipping someone else's brand assets - or
 * pulling them from a third-party URL past our own CSP - is not something a
 * marketing strip should do on its own initiative.
 *
 * The animation is CSS rather than JS. It runs for the life of the page, so it
 * belongs on the compositor where it costs nothing per frame; the global
 * prefers-reduced-motion rule in index.css freezes it.
 */
const ASSISTANTS = [
  'ChatGPT',
  'Claude',
  'Perplexity',
  'Gemini',
  'Copilot',
  'Google AI Overviews',
]

function Track({ ariaHidden = false }: { ariaHidden?: boolean }) {
  return (
    <ul
      className="flex shrink-0 items-center gap-12 pr-12"
      aria-hidden={ariaHidden || undefined}
    >
      {ASSISTANTS.map((name) => (
        <li
          key={name}
          className="whitespace-nowrap text-sm font-medium tracking-tight text-muted-foreground"
        >
          {name}
        </li>
      ))}
    </ul>
  )
}

export function AssistantMarquee() {
  return (
    <div className="border-y border-border bg-muted/20 py-6">
      <div className="mx-auto max-w-6xl px-6">
        <p className="mb-5 text-center text-xs uppercase tracking-widest text-muted-foreground">
          Scored against the assistants your customers actually ask
        </p>

        <div
          className="group relative overflow-hidden"
          // Fade the strip into the background at both edges instead of cutting
          // it off, so the loop seam is never the thing you notice.
          style={{
            maskImage:
              'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
            WebkitMaskImage:
              'linear-gradient(to right, transparent, black 8%, black 92%, transparent)',
          }}
        >
          <div className="flex w-max animate-marquee group-hover:[animation-play-state:paused] group-focus-within:[animation-play-state:paused]">
            {/* The second copy is what makes -50% seamless; it is decorative, so
                screen readers are shown the list exactly once. */}
            <Track />
            <Track ariaHidden />
          </div>
        </div>
      </div>
    </div>
  )
}
