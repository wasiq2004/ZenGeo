/**
 * Scroll-triggered reveals for the marketing page.
 *
 * Every component here collapses to a plain wrapper when the visitor has asked
 * for reduced motion - the content renders in its final state immediately
 * rather than animating faster. Motion is decoration; it never gates whether
 * something is readable.
 *
 * Reveals fire `once`, so scrolling back up does not replay them. A section
 * that re-animates every time it re-enters the viewport reads as a glitch.
 */
import { motion, useReducedMotion, type Variants } from 'motion/react'
import type { ReactNode } from 'react'

/** Slow-out easing - fast to start, settles gently. */
const EASE = [0.22, 1, 0.36, 1] as const

export function Reveal({
  children,
  className,
  delay = 0,
  y = 16,
}: {
  children: ReactNode
  className?: string
  delay?: number
  y?: number
}) {
  const reduced = useReducedMotion()

  if (reduced) return <div className={className}>{children}</div>

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.55, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  )
}

const containerVariants: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
}

/**
 * Staggers its `StaggerItem` children as the group scrolls into view.
 * `trigger="mount"` animates immediately instead - used for the hero, which is
 * already on screen at load and would otherwise never fire.
 */
export function Stagger({
  children,
  className,
  trigger = 'view',
}: {
  children: ReactNode
  className?: string
  trigger?: 'view' | 'mount'
}) {
  const reduced = useReducedMotion()

  if (reduced) return <div className={className}>{children}</div>

  return (
    <motion.div
      className={className}
      variants={containerVariants}
      initial="hidden"
      {...(trigger === 'mount'
        ? { animate: 'shown' }
        : { whileInView: 'shown', viewport: { once: true, amount: 0.2 } })}
    >
      {children}
    </motion.div>
  )
}

export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  const reduced = useReducedMotion()

  if (reduced) return <div className={className}>{children}</div>

  return (
    <motion.div className={className} variants={itemVariants}>
      {children}
    </motion.div>
  )
}
