import { useEffect, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'

/**
 * Drives the cursor spotlight on `.mk-spotlight` cards inside this subtree.
 *
 * One delegated listener on the wrapper rather than one per card: the landing
 * page has ~20 cards, and twenty pointermove handlers all firing on the same
 * events is twenty times the work for identical results.
 *
 * Writes are batched into a single rAF, so a burst of pointermove events
 * between frames collapses to one style write. Only two custom properties
 * change, and the gradient reading them lives on a ::before with its own
 * layer — no layout, no reflow.
 *
 * Coordinates are per-card and relative to that card, so the light is where
 * the pointer is rather than where the page thinks it is.
 */
export function SpotlightLayer({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion()

  useEffect(() => {
    // A light chasing the cursor is motion even though no keyframe drives it.
    // The CSS hides it under reduced motion; not attaching the listener at all
    // means we are not doing the work either.
    if (reduced) return

    let frame = 0
    let target: HTMLElement | null = null
    let x = 0
    let y = 0

    const paint = () => {
      frame = 0
      if (!target) return
      target.style.setProperty('--mx', `${x}px`)
      target.style.setProperty('--my', `${y}px`)
    }

    const onMove = (event: PointerEvent) => {
      const card = (event.target as Element | null)?.closest<HTMLElement>('.mk-spotlight')
      if (!card) return
      const rect = card.getBoundingClientRect()
      target = card
      x = event.clientX - rect.left
      y = event.clientY - rect.top
      if (!frame) frame = requestAnimationFrame(paint)
    }

    // Passive: this never calls preventDefault, and saying so lets the browser
    // keep scrolling off the main thread.
    document.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      document.removeEventListener('pointermove', onMove)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [reduced])

  return <>{children}</>
}
