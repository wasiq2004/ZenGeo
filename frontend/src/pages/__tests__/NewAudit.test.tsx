import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setAccessToken } from '@/lib/api'
import NewAudit from '@/pages/app/NewAudit'
import { mockFetch, renderWithProviders, screen, userEvent, waitFor } from '@/test/utils'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const verifiedUser = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'person@example.com',
  full_name: null,
  role: 'user' as const,
  is_active: true,
  is_email_verified: true,
  mfa_enabled: false,
  notify_audit_complete: true,
  created_at: new Date().toISOString(),
  last_login_at: null,
}

function session(user = verifiedUser) {
  return { access_token: 'token', token_type: 'bearer', expires_in: 900, user }
}

function routes(overrides: Record<string, { status?: number; body?: unknown }> = {}) {
  return mockFetch({
    'POST /auth/refresh': { body: session() },
    'GET /auth/me': { body: verifiedUser },
    'GET /businesses': { body: [] },
    'GET /llm-keys': { body: [] },
    ...overrides,
  })
}

describe('Audit wizard', () => {
  beforeEach(() => {
    navigate.mockClear()
    setAccessToken(null)
  })

  it('will not advance past step one without a business name', async () => {
    vi.stubGlobal('fetch', routes())
    await renderWithProviders(<NewAudit />)

    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))

    expect(await screen.findByText(/enter your business or brand name/i)).toBeInTheDocument()
    // Still on step one.
    expect(screen.getByLabelText(/business or brand name/i)).toBeInTheDocument()
  })

  it('will not advance past the website step without a URL', async () => {
    vi.stubGlobal('fetch', routes())
    await renderWithProviders(<NewAudit />)

    await userEvent.type(await screen.findByLabelText(/business or brand name/i), 'Acme')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))

    expect(await screen.findByText(/enter your website address/i)).toBeInTheDocument()
  })

  it('tells the user Share of Voice is locked when no key is connected', async () => {
    vi.stubGlobal('fetch', routes())
    await renderWithProviders(<NewAudit />)

    await userEvent.type(await screen.findByLabelText(/business or brand name/i), 'Acme')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.type(await screen.findByLabelText(/website address/i), 'https://acme.test')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))

    expect(await screen.findByText(/no ai provider connected/i)).toBeInTheDocument()
    expect(screen.getByText(/spread across the other six pillars/i)).toBeInTheDocument()
  })

  it('shows the planned call count before anything is spent', async () => {
    vi.stubGlobal(
      'fetch',
      routes({
        'GET /llm-keys': {
          body: [
            {
              id: 'k1',
              provider: 'openai',
              label: 'default',
              key_preview: 'sk-...abcd',
              model: null,
              is_active: true,
              use_web_search: false,
              last_validated_at: null,
              last_used_at: null,
              created_at: new Date().toISOString(),
            },
            {
              id: 'k2',
              provider: 'anthropic',
              label: 'default',
              key_preview: 'sk-ant-...wxyz',
              model: null,
              is_active: true,
              use_web_search: true,
              last_validated_at: null,
              last_used_at: null,
              created_at: new Date().toISOString(),
            },
          ],
        },
      }),
    )
    await renderWithProviders(<NewAudit />)

    await userEvent.type(await screen.findByLabelText(/business or brand name/i), 'Acme')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.type(await screen.findByLabelText(/website address/i), 'https://acme.test')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))

    await userEvent.type(
      await screen.findByLabelText(/your target prompts/i),
      'best analytics tool\nalternatives to mixpanel\ncheapest product analytics',
    )

    // 3 prompts x 2 providers = 6 calls, stated up front. Not a cap - the
    // spend is on the user's own key, so it just has to be visible.
    expect(await screen.findByText(/3 prompts × 2 providers =/i)).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
  })

  it('submits the whole questionnaire and navigates to the audit', async () => {
    const fetchSpy = routes({
      'POST /audits': { status: 201, body: { audit: { id: 'audit-123' }, message: 'queued' } },
    })
    vi.stubGlobal('fetch', fetchSpy)
    await renderWithProviders(<NewAudit />)

    await userEvent.type(await screen.findByLabelText(/business or brand name/i), 'Acme Analytics')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.type(await screen.findByLabelText(/website address/i), 'https://acme.test')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))
    await userEvent.type(await screen.findByLabelText(/your target prompts/i), 'best analytics tool')
    await userEvent.click(screen.getByRole('button', { name: /continue/i }))
    await userEvent.click(await screen.findByRole('button', { name: /start the audit/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/app/audits/audit-123'))

    const call = fetchSpy.mock.calls.find(([url]) => String(url).includes('/audits'))
    const body = JSON.parse(String((call?.[1] as RequestInit)?.body))
    expect(body.business.name).toBe('Acme Analytics')
    expect(body.business.website_url).toBe('https://acme.test')
    expect(body.questionnaire.target_prompts).toEqual(['best analytics tool'])
    expect(body.questionnaire.goal).toBe('health_check')
  })

  it('opens the wizard without any email confirmation step', async () => {
    // This deployment sends no email, so there is nothing to confirm and no
    // gate in front of the wizard. An account with the flag unset must still
    // reach the form - the inverse of what this test used to assert.
    const unconfirmed = { ...verifiedUser, is_email_verified: false }
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'POST /auth/refresh': { body: session(unconfirmed) },
        'GET /auth/me': { body: unconfirmed },
        'GET /businesses': { body: [] },
        'GET /llm-keys': { body: [] },
      }),
    )
    await renderWithProviders(<NewAudit />)

    expect(await screen.findByLabelText(/business or brand name/i)).toBeInTheDocument()
    expect(screen.queryByText(/confirm your email/i)).not.toBeInTheDocument()
  })
})
