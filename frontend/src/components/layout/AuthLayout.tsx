import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    // Sign-in and sign-up sit on the marketing side of the funnel and are seen
    // back-to-back with the landing page, so they wear the same type pairing.
    <div className="glow-surface mk-surface flex min-h-screen flex-col bg-background">
      <header className="flex items-center justify-between px-6 py-5">
        <Link to="/" className="rounded-md focus-visible:ring-2 focus-visible:ring-ring">
          <Logo />
        </Link>
        <div className="flex items-center gap-2">
          {/* The logo already links home, but nothing says so. Someone who
              opened this page by mistake needs a visible way out, not a
              convention they have to know. */}
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft aria-hidden="true" className="size-4" />
            Back to home
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="flex flex-1 items-start justify-center px-6 pb-16 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm animate-fade-in">
          <div className="mb-6 space-y-1.5 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
          </div>

          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">{children}</div>

          {footer && <div className="mt-5 text-center text-sm text-muted-foreground">{footer}</div>}
        </div>
      </main>
    </div>
  )
}
