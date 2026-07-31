/**
 * A number that counts up from zero the first time it scrolls into view.
 *
 * The tween writes straight to the DOM node instead of going through state:
 * a 1.4s count at 60fps is ~85 renders per tile, and a row of tiles would make
 * that a few hundred renders for something purely decorative.
 *
 * The final value is what React renders, so it is correct before the effect
 * runs and stays correct with JavaScript animations disabled - which is also
 * what makes it assertable in tests.
 */
import { animate, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef } from 'react'

export function CountUp({
  to,
  duration = 1.4,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
}: {
  to: number
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.5 })
  const reduced = useReducedMotion()

  const format = (value: number) => `${prefix}${value.toFixed(decimals)}${suffix}`

  useEffect(() => {
    const node = ref.current
    if (!node || reduced || !inView) return

    const controls = animate(0, to, {
      duration,
      ease: 'easeOut',
      onUpdate: (value) => {
        node.textContent = format(value)
      },
    })
    // Land exactly on the target - the last frame can stop a hair short.
    return () => {
      controls.stop()
      node.textContent = format(to)
    }
    // `format` is derived from the formatting props listed here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, reduced, to, duration, decimals, prefix, suffix])

  return (
    <span ref={ref} className={className}>
      {format(to)}
    </span>
  )
}
