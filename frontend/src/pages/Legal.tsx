import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { CONTACT } from '@/lib/contact'

/**
 * Privacy policy and terms.
 *
 * These describe what the product actually does — self-hosted, BYOK, keys
 * encrypted at rest, no email sent — rather than boilerplate copied from a
 * generator. That accuracy is the point: a policy that claims practices you do
 * not follow is worse than none, because it is a statement you can be held to.
 *
 * They are still not legal advice. Have a solicitor read them before you rely
 * on them commercially.
 */

function LegalShell({ title, updated, children }: {
  title: string
  updated: string
  children: React.ReactNode
}) {
  return (
    <div className="mk-surface min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
          <Link to="/" className="rounded-md focus-visible:ring-2 focus-visible:ring-ring">
            <Logo />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft aria-hidden="true" className="size-4" />
              Back to home
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-14">
        <h1 className="text-3xl font-extrabold tracking-[-0.025em] sm:text-4xl">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated {updated}</p>

        <div className="mt-10 space-y-8 text-sm leading-relaxed text-muted-foreground [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-foreground [&_strong]:text-foreground">
          {children}
        </div>

        <div className="mt-14 rounded-xl border border-border bg-card p-6">
          <h2 className="text-base font-semibold text-foreground">Questions about this?</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Email{' '}
            <a href={`mailto:${CONTACT.email}`} className="font-medium text-primary hover:underline">
              {CONTACT.email}
            </a>{' '}
            or call{' '}
            <a href={`tel:${CONTACT.phoneHref}`} className="font-medium text-primary hover:underline">
              {CONTACT.phoneDisplay}
            </a>
            .
          </p>
        </div>
      </main>
    </div>
  )
}

export function PrivacyPolicy() {
  return (
    <LegalShell title="Privacy policy" updated="3 August 2026">
      <section className="space-y-3">
        <h2>What we hold</h2>
        <p>
          An account is an email address, an optional name, and a password stored only as an
          Argon2id hash — we cannot read it, and neither can an administrator. Beyond that we hold
          the businesses you add, the audits you run, and the reports those audits produce.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Your AI provider keys</h2>
        <p>
          Keys you connect are <strong>encrypted before they reach the database</strong> and
          decrypted only in memory, inside the process making your audit call. They are never
          written to logs, never returned to the browser after you save them, and are not visible to
          anyone else — administrators included. There is no endpoint anywhere in this product that
          returns a stored key. You can delete one permanently at any time.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Who your data goes to</h2>
        <p>
          When you run a Share of Voice test, your target prompts are sent to the AI providers you
          chose, using <strong>your own API key</strong>. That call happens on your account with
          that provider and is governed by their terms, not ours. We do not proxy it through a
          shared key, and we do not train anything on your data.
        </p>
        <p>
          Audits fetch the pages of the website you asked us to audit. Nothing else leaves this
          server.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Email</h2>
        <p>
          <strong>This deployment sends no email at all.</strong> There is no marketing list, no
          transactional mail, and no third-party mail provider holding your address. It follows that
          there is no self-service password reset — see the terms below.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Retention and deletion</h2>
        <p>
          You can export everything we hold about you, or delete your account outright, from
          Settings. Deletion is immediate and cascades: businesses, audits, stored PDF reports and
          encrypted keys all go with it, and it cannot be undone. An administrator can also delete
          an account on request.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Administrator access</h2>
        <p>
          Administrators can see your account details, your audits and your reports in order to
          support you. They can also sign in as you to reproduce a problem — that session is capped
          at 30 minutes, cannot change your password, email or delete your account, and is recorded
          in an append-only audit log against the administrator&apos;s name.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Contact</h2>
        <p>
          For any request about your data — access, correction or erasure — email{' '}
          <a href={`mailto:${CONTACT.email}`} className="font-medium text-primary hover:underline">
            {CONTACT.email}
          </a>
          .
        </p>
      </section>
    </LegalShell>
  )
}

export function Terms() {
  return (
    <LegalShell title="Terms and conditions" updated="3 August 2026">
      <section className="space-y-3">
        <h2>What the service does</h2>
        <p>
          We score how visible and citable a website is to AI assistants across seven weighted
          pillars, and return a report with prioritised fixes. The score is an assessment against
          our own published method — it is not a guarantee of any outcome in any AI assistant, and
          those assistants change without notice.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Your account</h2>
        <p>
          You are responsible for what happens under your account and for keeping your password
          safe. <strong>There is no self-service password reset</strong>, because this deployment
          sends no email — if you are locked out, an administrator sets a new password and gives it
          to you directly. Contact details are below.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Bring your own keys</h2>
        <p>
          Share of Voice testing runs on API keys you supply. Any cost falls on your account with
          that provider, which is what keeps this tool free and uncapped — we do not limit how many
          prompts or providers you test. You are responsible for staying within the terms of the
          providers whose keys you connect.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Acceptable use</h2>
        <p>
          Audit sites you own or have permission to audit. Do not use the service to attack,
          overload or scrape a third party, and do not attempt to reach other users&apos; data. We
          may suspend an account that does.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Availability and liability</h2>
        <p>
          The service is provided as-is. We do not promise uninterrupted availability, and audits
          depend on third-party AI providers that may be slow, rate-limited or unavailable. To the
          extent permitted by law, we are not liable for indirect or consequential loss arising from
          use of the service or reliance on a score.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Changes</h2>
        <p>
          We may update these terms as the product changes. The date at the top reflects the last
          revision.
        </p>
      </section>

      <section className="space-y-3">
        <h2>Contact</h2>
        <p>
          Email{' '}
          <a href={`mailto:${CONTACT.email}`} className="font-medium text-primary hover:underline">
            {CONTACT.email}
          </a>{' '}
          or call{' '}
          <a href={`tel:${CONTACT.phoneHref}`} className="font-medium text-primary hover:underline">
            {CONTACT.phoneDisplay}
          </a>
          .
        </p>
      </section>
    </LegalShell>
  )
}
