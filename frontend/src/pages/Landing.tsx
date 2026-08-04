import {
  ArrowRight,
  BookOpenText,
  Bot,
  Check,
  FileText,
  Gauge,
  KeyRound,
  Link2,
  ListChecks,
  Lock,
  Mail,
  Menu,
  Phone,
  Quote,
  Radar,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AssistantMarquee } from '@/components/landing/AssistantMarquee'
import { PreviewStats, ScorePreview } from '@/components/landing/ScorePreview'
import { StepsToScore } from '@/components/landing/StepsToScore'
import { WeightBreakdown } from '@/components/landing/WeightBreakdown'
import { Logo } from '@/components/Logo'
import { CONTACT } from '@/lib/contact'
import { Reveal, Stagger, StaggerItem } from '@/components/motion/Reveal'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'
import { PILLARS } from '@/lib/geo'
import { cn } from '@/lib/utils'

const PILLAR_ICONS: Record<string, typeof Bot> = {
  crawlability: Bot,
  llms_txt: FileText,
  structured_data: ListChecks,
  extractability: BookOpenText,
  evidence: Quote,
  entity_authority: Link2,
  share_of_voice: Radar,
}

const METHOD = [
  {
    title: 'Describe your business',
    body: 'A short guided form: what you sell, who you compete with, and the questions your customers would type into an assistant.',
  },
  {
    title: 'We scan your site',
    body: 'Six automated pillars run against your live pages — bot rules, llms.txt, schema, structure, evidence and entity signals.',
  },
  {
    title: 'We test the assistants',
    body: 'Your prompts are run for real. We record whether you were mentioned, cited, and who showed up instead.',
  },
  {
    title: 'You get a plan',
    body: 'A 0–100 score, a per-pillar breakdown, and prioritised fixes ranked by impact. Downloadable as a PDF.',
  },
]

const FAQ = [
  {
    q: 'What is GEO, and how is it different from SEO?',
    a: 'SEO optimises for a ranked list of links. GEO optimises for being the source an assistant reads, trusts and cites inside a written answer — which rewards machine-readable facts and verifiable evidence far more than keyword density.',
  },
  {
    q: 'Why do I need to bring my own API key?',
    a: 'Share of Voice sends your prompts to real assistants. Using your own key keeps the tool free, keeps your prompts on your own account, and means nobody caps how much you test.',
  },
  {
    q: 'Is my API key safe?',
    a: 'Keys are encrypted before they reach the database and decrypted only in memory, for your audit call. They are never logged, never returned to the browser, and not visible to anyone — administrators included.',
  },
  {
    q: 'What if I do not connect a key?',
    a: 'Everything else still runs. Share of Voice is skipped and its 15% is redistributed across the other six, so your score stays on a true 0–100 scale — and the report says so.',
  },
  {
    q: 'How long does an audit take?',
    a: 'The automated pillars finish in under a minute. Share of Voice depends on how many prompts and providers you chose.',
  },
]

/**
 * True once the observed element has scrolled off the top of the viewport.
 *
 * An IntersectionObserver on a sentinel rather than a scroll listener: the
 * browser does the work off the main thread and calls back only on the one
 * transition we care about, instead of on every scroll frame.
 */
function useScrolledPast<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [passed, setPassed] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return
        setPassed(!entry.isIntersecting && entry.boundingClientRect.top <= 0)
      },
      { threshold: 0 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return [ref, passed] as const
}

function Nav({ solid }: { solid: boolean }) {
  const { isAuthenticated, isAdmin } = useAuth()
  const [open, setOpen] = useState(false)
  const appHref = isAdmin ? '/admin' : '/app'

  const links = [
    { href: '#how', label: 'How it works' },
    { href: '#pillars', label: 'Scoring' },
    { href: '#byok', label: 'Your keys' },
    { href: '#faq', label: 'FAQ' },
  ]

  return (
    <header
      className={cn(
        'sticky top-0 z-40 transition-[background-color,border-color,backdrop-filter,box-shadow] duration-300',
        // Over the hero the bar is invisible and the mesh shows through; once
        // real content would slide under it, it takes on a surface so the links
        // stay legible against whatever is passing behind.
        solid || open
          ? 'border-b border-border/70 bg-background/80 shadow-sm backdrop-blur-md'
          : 'border-b border-transparent bg-transparent',
      )}
    >
      <nav
        className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6"
        aria-label="Main"
      >
        <Link to="/" className="rounded-md focus-visible:ring-2 focus-visible:ring-ring">
          <Logo />
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle className="hidden sm:inline-flex" />
          {isAuthenticated ? (
            <Button asChild size="sm" className="cta-glow">
              <Link to={appHref}>
                Open dashboard <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
                <Link to="/login">Sign in</Link>
              </Button>
              <Button asChild size="sm" className="cta-glow">
                <Link to="/signup">Start free audit</Link>
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? 'Close menu' : 'Open menu'}
          >
            {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </Button>
        </div>
      </nav>

      {open && (
        <div id="mobile-nav" className="border-t border-border px-6 py-3 md:hidden">
          <ul className="space-y-1">
            {links.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-md px-2 py-2 text-sm text-muted-foreground hover:text-foreground"
                >
                  {link.label}
                </a>
              </li>
            ))}
            <li>
              <Link
                to="/login"
                className="block rounded-md px-2 py-2 text-sm text-muted-foreground hover:text-foreground"
              >
                Sign in
              </Link>
            </li>
          </ul>
        </div>
      )}
    </header>
  )
}

/** Drifting colour fields behind the hero. Purely decorative. */
function HeroMesh() {
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden" aria-hidden="true">
      <div
        className="mesh-blob animate-blob-drift-a -left-24 -top-32 size-[38rem]"
        style={{
          background:
            'radial-gradient(circle, color-mix(in srgb, var(--mk-cyan) 42%, transparent), transparent 70%)',
        }}
      />
      <div
        className="mesh-blob animate-blob-drift-b -right-32 -top-16 size-[34rem]"
        style={{
          background:
            'radial-gradient(circle, color-mix(in srgb, var(--mk-gold) 30%, transparent), transparent 70%)',
        }}
      />
      <div
        className="mesh-blob animate-blob-drift-b bottom-[-14rem] left-1/3 size-[30rem] [animation-delay:-8s]"
        style={{
          background:
            'radial-gradient(circle, color-mix(in srgb, var(--mk-cyan-soft) 30%, transparent), transparent 70%)',
        }}
      />
    </div>
  )
}

function Hero() {
  const reduced = useReducedMotion()

  return (
    // `isolate` keeps the mesh's negative z-index inside this section - without
    // its own stacking context the blobs slide behind the page background and
    // disappear entirely.
    <section className="relative isolate overflow-hidden border-b border-border">
      <HeroMesh />
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
        <Stagger trigger="mount" className="mx-auto max-w-3xl text-center">
          <StaggerItem>
            <Badge variant="outline" className="mb-6 gap-1.5 py-1 pl-1.5 pr-3">
              <span
                className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                style={{
                  background: 'color-mix(in srgb, var(--mk-cyan) 16%, transparent)',
                  color: 'var(--mk-cyan)',
                }}
              >
                Free
              </span>
              Bring your own API key — no usage caps
            </Badge>
          </StaggerItem>

          <StaggerItem>
            <h1 className="text-balance text-4xl font-extrabold leading-[1.06] tracking-[-0.03em] sm:text-5xl md:text-6xl">
              When an AI answers your customer&apos;s question,
              <span className="mk-gradient-text"> is it citing you?</span>
            </h1>
          </StaggerItem>

          <StaggerItem>
            <p className="mx-auto mt-6 max-w-2xl text-pretty text-lg leading-relaxed text-muted-foreground">
              Search is moving inside ChatGPT, Claude, Perplexity and Gemini — where there is no
              page two, only the sources the model chose to trust. CheckGEO.ai scores how visible
              and citable your business is to those models, and tells you exactly what to fix.
            </p>
          </StaggerItem>

          <StaggerItem>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button asChild size="lg" className="mk-gradient-bg cta-glow w-full border-0 text-slate-900 sm:w-auto">
                <Link to="/signup">
                  Run your free audit <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="w-full sm:w-auto">
                <a href="#pillars">See what we measure</a>
              </Button>
            </div>
          </StaggerItem>

          <StaggerItem>
            <p className="mt-4 text-xs text-muted-foreground">
              No credit card. No sales call. Your keys stay yours.
            </p>
          </StaggerItem>
        </Stagger>

        {/* The mock lifts in slightly after the copy, so the eye reads the
            headline first and finds the product already there when it arrives. */}
        <motion.div
          className="mx-auto mt-16 max-w-4xl"
          initial={reduced ? false : { opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduced ? { duration: 0 } : { duration: 0.7, delay: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          <ScorePreview />
          <PreviewStats />
        </motion.div>
      </div>
    </section>
  )
}

function HowItWorks() {
  return (
    <section id="how" className="border-b border-border py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-6">
        <Reveal className="max-w-2xl">
          <h2 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">
            Four steps, one honest number
          </h2>
          <p className="mt-3 text-pretty text-muted-foreground">
            No black box. Every point in your score traces back to a specific check you can
            reproduce yourself.
          </p>
        </Reveal>

        <Stagger className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {METHOD.map((step, index) => (
            <StaggerItem key={step.title}>
              <Card className="mk-lift h-full">
                <CardContent className="space-y-3 p-5">
                  <span className="inline-flex size-8 items-center justify-center rounded-lg bg-primary/12 text-sm font-semibold text-primary">
                    {index + 1}
                  </span>
                  <h3 className="font-medium leading-snug">{step.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
                </CardContent>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  )
}

function Pillars() {
  return (
    <section id="pillars" className="border-b border-border bg-muted/25 py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-6">
        <Reveal className="max-w-2xl">
          <h2 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">
            Seven weighted pillars
          </h2>
          <p className="mt-3 text-pretty text-muted-foreground">
            Scored 0–100 each, then combined by weight. You always see the sub-scores.
          </p>
        </Reveal>

        <Stagger className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PILLARS.map((pillar) => {
            const Icon = PILLAR_ICONS[pillar.key] ?? Gauge
            return (
              <StaggerItem key={pillar.key}>
                <Card className="mk-lift h-full">
                  <CardContent className="space-y-3 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <span className="inline-flex size-9 items-center justify-center rounded-lg bg-primary/12 text-primary">
                        <Icon className="size-4.5" aria-hidden="true" />
                      </span>
                      <Badge variant="secondary" className="tabular-nums">
                        {Math.round(pillar.weight * 100)}%
                      </Badge>
                    </div>
                    <h3 className="font-medium leading-snug">{pillar.name}</h3>
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      {pillar.description}
                    </p>
                  </CardContent>
                </Card>
              </StaggerItem>
            )
          })}

          <StaggerItem>
            <Card className="h-full border-dashed bg-transparent">
              <CardContent className="flex h-full flex-col justify-center gap-2 p-5">
                <h3 className="font-medium leading-snug">Bands</h3>
                <ul className="space-y-1.5 text-sm text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-band-poor" /> 0–39 Poor
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-band-fair" /> 40–59 Needs Work
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-band-good" /> 60–79 Good
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-band-excellent" /> 80–100 Excellent
                  </li>
                </ul>
              </CardContent>
            </Card>
          </StaggerItem>
        </Stagger>
      </div>
    </section>
  )
}

function Byok() {
  const points = [
    {
      icon: Lock,
      title: 'Encrypted before storage',
      body: 'Your key is encrypted with an authenticated cipher the moment it arrives, and only decrypted in memory inside the process making your own audit call.',
    },
    {
      icon: ShieldCheck,
      title: 'Never shown again, never shared',
      body: 'After saving, the app only ever displays a masked preview. Administrators can see that a key exists — never its value.',
    },
    {
      icon: Sparkles,
      title: 'No caps on what you test',
      body: 'Because the cost is on your account, you decide how many target prompts and which providers to run. We only pace the calls so nobody gets rate-limited.',
    },
    {
      icon: KeyRound,
      title: 'Delete whenever',
      body: 'Removing a key is a hard delete, not a flag. Skip this step entirely and the other six pillars still produce a full score.',
    },
  ]

  return (
    <section id="byok" className="border-b border-border py-20 sm:py-24">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 lg:grid-cols-2">
        <Reveal>
          <Badge variant="outline" className="mb-4">
            Bring your own key
          </Badge>
          <h2 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">
            Your keys. Your account. Your limits.
          </h2>
          <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">
            Live AI testing is the part of this audit that actually costs money — so we let you
            pay for it directly, at cost, on your own provider account. That is what keeps the
            tool free and keeps you from bumping into somebody else&apos;s quota.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {['OpenAI', 'Anthropic', 'Perplexity'].map((name) => (
              <Badge key={name} variant="secondary" className="gap-1.5 py-1">
                <Check className="size-3" aria-hidden="true" />
                {name}
              </Badge>
            ))}
          </div>
        </Reveal>

        <Stagger className="grid gap-4 sm:grid-cols-2">
          {points.map((point) => (
            <StaggerItem key={point.title}>
              <Card className="mk-lift h-full">
                <CardContent className="space-y-2 p-5">
                  <point.icon className="size-4.5 text-primary" aria-hidden="true" />
                  <h3 className="text-sm font-medium">{point.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{point.body}</p>
                </CardContent>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  )
}

function Faq() {
  return (
    <section id="faq" className="border-b border-border bg-muted/25 py-20 sm:py-24">
      <div className="mx-auto max-w-3xl px-6">
        <Reveal>
          <h2 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">Questions</h2>
        </Reveal>
        <dl className="mt-10 space-y-8">
          {FAQ.map((item, index) => (
            <Reveal key={item.q} delay={index * 0.04}>
              <dt className="font-medium leading-snug">{item.q}</dt>
              <dd className="mt-2 text-pretty leading-relaxed text-muted-foreground">{item.a}</dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t border-border bg-muted/20">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-10 lg:grid-cols-[1.6fr_repeat(3,1fr)]">
          <div>
            <Logo />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-muted-foreground">
              Measure how visible and citable your business is inside AI answers, then fix what the
              score tells you to fix.
            </p>
            <div className="mt-5 space-y-2 text-sm">
              <a
                href={`mailto:${CONTACT.email}`}
                className="flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
              >
                <Mail aria-hidden="true" className="size-4 shrink-0" />
                {CONTACT.email}
              </a>
              <a
                href={`tel:${CONTACT.phoneHref}`}
                className="flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
              >
                <Phone aria-hidden="true" className="size-4 shrink-0" />
                {CONTACT.phoneDisplay}
              </a>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold">Product</h3>
            <ul className="mt-4 space-y-2.5 text-sm">
              {[
                { label: 'How it works', href: '#how' },
                { label: 'What we measure', href: '#pillars' },
                { label: 'Bring your own key', href: '#byok' },
                { label: 'Questions', href: '#faq' },
              ].map((l) => (
                <li key={l.href}>
                  <a
                    href={l.href}
                    className="text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h3 className="text-sm font-semibold">Account</h3>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li>
                <Link
                  to="/signup"
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  Create account
                </Link>
              </li>
              <li>
                <Link
                  to="/login"
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  Sign in
                </Link>
              </li>
              <li>
                <a
                  href={`mailto:${CONTACT.email}?subject=Support%20request`}
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  Support
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="text-sm font-semibold">Legal</h3>
            <ul className="mt-4 space-y-2.5 text-sm">
              <li>
                <Link
                  to="/privacy"
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  Privacy policy
                </Link>
              </li>
              <li>
                <Link
                  to="/terms"
                  className="text-muted-foreground transition-colors hover:text-foreground"
                >
                  Terms &amp; conditions
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-border pt-7 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>© {new Date().getFullYear()} CheckGEO.ai. All rights reserved.</span>
          <span>Self-hosted. Your data and your API keys stay on your own server.</span>
        </div>
      </div>
    </footer>
  )
}

export default function Landing() {
  const [sentinelRef, pastHero] = useScrolledPast<HTMLDivElement>()

  return (
    <div className="mk-surface min-h-screen bg-background">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Nav solid={pastHero} />
      <main id="main">
        <Hero />
        {/* Sits on the hero's bottom edge; the nav solidifies once it goes by. */}
        <div ref={sentinelRef} aria-hidden="true" className="h-px" />
        <AssistantMarquee />
        <HowItWorks />
        <WeightBreakdown />
        <Pillars />
        <Byok />
        <StepsToScore />
        <Faq />
      </main>
      <Footer />
    </div>
  )
}
