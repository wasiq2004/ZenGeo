import { describe, expect, it, vi } from 'vitest'
import Landing from '@/pages/Landing'
import { PILLARS } from '@/lib/geo'
import { renderWithProviders, screen } from '@/test/utils'

describe('Landing page', () => {
  it('renders the hero and both primary calls to action', async () => {
    // No session cookie in tests: the boot-time refresh should just fail.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))

    await renderWithProviders(<Landing />)

    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(/is it citing you/i)
    expect(screen.getByRole('link', { name: /run your free audit/i })).toHaveAttribute(
      'href',
      '/signup',
    )
    expect(screen.getAllByRole('link', { name: /sign in/i }).length).toBeGreaterThan(0)
  })

  it('documents every scoring pillar with its weight', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    await renderWithProviders(<Landing />)

    for (const pillar of PILLARS) {
      expect(screen.getByRole('heading', { name: pillar.name })).toBeInTheDocument()
    }
    // Weights must sum to 100% or the composite score is meaningless.
    const total = PILLARS.reduce((sum, p) => sum + p.weight, 0)
    expect(total).toBeCloseTo(1, 5)
  })

  it('exposes a skip link for keyboard users', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    await renderWithProviders(<Landing />)
    expect(screen.getByRole('link', { name: /skip to content/i })).toHaveAttribute('href', '#main')
  })

  it('wears the marketing font rather than inheriting the app font', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    const { container } = await renderWithProviders(<Landing />)

    // `font-app` is the inherited default, so the marketing tree has to opt in
    // at its root. Losing this class is the one way the two families can
    // silently converge - hence a test rather than a code comment.
    expect(container.firstElementChild).toHaveClass('font-landing')
  })

  it('walks through the three steps to a score in place of a pricing table', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    await renderWithProviders(<Landing />)

    expect(
      screen.getByRole('heading', { name: /see your geo score in minutes/i }),
    ).toBeInTheDocument()
    for (const step of [/add your business/i, /connect your ai keys/i, /get your score \+ pdf/i]) {
      expect(screen.getByRole('heading', { name: step })).toBeInTheDocument()
    }
    // The product is free, so nothing on the page should read as a price.
    expect(screen.queryByRole('heading', { name: /pricing|plans/i })).not.toBeInTheDocument()
  })

  it('announces each assistant in the marquee exactly once', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    await renderWithProviders(<Landing />)

    // Two copies exist in the DOM - that duplicate is what makes the -50%
    // loop seamless...
    expect(screen.getAllByText('Claude')).toHaveLength(2)

    // ...but `getAllByRole` reflects the accessibility tree, which drops the
    // aria-hidden copy. A screen reader reads the assistants once rather than
    // stuttering through them twice.
    const announced = screen
      .getAllByRole('list')
      .filter((list) => list.textContent?.includes('Claude'))
    expect(announced).toHaveLength(1)
    expect(announced[0]).toHaveTextContent('Perplexity')
  })

  it('renders the sample report with the pillars on one hue and the band named in text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    const { container } = await renderWithProviders(<Landing />)

    // The band is stated in words, so colour is never the only carrier.
    expect(screen.getByText('Needs Work')).toBeInTheDocument()

    // Pillar bars are nominal categories: one hue across all of them. If a
    // future edit colours them by score, this catches it.
    const bars = container.querySelectorAll<HTMLElement>('[style*="--viz-series-1"]')
    expect(bars.length).toBeGreaterThan(0)
    for (const bar of bars) {
      expect(bar.style.backgroundColor).toBe('var(--viz-series-1)')
    }
  })
})
