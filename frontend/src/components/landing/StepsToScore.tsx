/**
 * "See your GEO score in minutes" - the step-through that sits where a pricing
 * table would normally go. The product is free, so the question a visitor has
 * at this point in the page is "what do I actually have to do?", not "what does
 * it cost".
 *
 * The connecting line draws itself as the section scrolls in, and each step
 * lands after it. Under reduced motion the line is simply already drawn.
 */
import { motion, useReducedMotion } from 'motion/react'
import { ArrowRight, FileBarChart, KeyRound, Building2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Reveal, Stagger, StaggerItem } from '@/components/motion/Reveal'
import { Button } from '@/components/ui/button'

const STEPS = [
  {
    icon: Building2,
    title: 'Add your business',
    body: 'A short guided form: your site, what you sell, who you compete with, and the questions a customer would type into an assistant.',
    duration: '~2 minutes',
  },
  {
    icon: KeyRound,
    title: 'Connect your AI keys',
    body: 'Optional. Paste an OpenAI, Anthropic or Perplexity key and we run your prompts for real, on your account. Skip it and the other six pillars still score.',
    duration: '~1 minute',
  },
  {
    icon: FileBarChart,
    title: 'Get your score + PDF',
    body: 'A 0-100 composite with a per-pillar breakdown and a prioritised list of fixes, split into quick wins, medium effort and strategic work.',
    duration: 'Under a minute',
  },
]

export function StepsToScore() {
  const reduced = useReducedMotion()

  return (
    <section id="start" className="border-b border-border py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-6">
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
            See your GEO score in minutes
          </h2>
          <p className="mt-3 text-pretty text-muted-foreground">
            No pricing page to read - the audit is free and runs on your own API key. Three steps
            from here to a report.
          </p>
        </Reveal>

        <div className="relative mt-14">
          {/* Rail behind the step markers. Hidden on small screens, where the
              steps stack and a horizontal line would point nowhere. */}
          <div className="pointer-events-none absolute inset-x-0 top-6 hidden lg:block" aria-hidden="true">
            <div className="mx-auto h-px w-2/3 overflow-hidden bg-border">
              <motion.div
                className="h-full origin-left bg-primary/50"
                initial={{ scaleX: reduced ? 1 : 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true, amount: 0.5 }}
                transition={reduced ? { duration: 0 } : { duration: 1.1, ease: 'easeInOut' }}
              />
            </div>
          </div>

          <Stagger className="grid gap-8 lg:grid-cols-3">
            {STEPS.map((step, index) => (
              <StaggerItem key={step.title} className="relative text-center">
                <span className="relative z-10 mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-card shadow-sm">
                  <step.icon className="size-5 text-primary" aria-hidden="true" />
                </span>
                <p className="mt-5 text-xs font-medium uppercase tracking-widest text-muted-foreground">
                  Step {index + 1} &middot; {step.duration}
                </p>
                <h3 className="mt-2 text-lg font-medium leading-snug">{step.title}</h3>
                <p className="mx-auto mt-2 max-w-sm text-pretty text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
              </StaggerItem>
            ))}
          </Stagger>
        </div>

        <Reveal className="mt-14 text-center" delay={0.1}>
          <Button asChild size="lg" className="cta-glow">
            <Link to="/signup">
              Start your free audit <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <p className="mt-3 text-xs text-muted-foreground">
            No credit card. No sales call. Your keys stay yours.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
