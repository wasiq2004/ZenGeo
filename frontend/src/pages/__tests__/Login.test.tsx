import { beforeEach, describe, expect, it, vi } from 'vitest'
import Login from '@/pages/Login'
import { setAccessToken } from '@/lib/api'
import { mockFetch, renderWithProviders, screen, userEvent, waitFor } from '@/test/utils'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

function session(role: 'user' | 'admin') {
  return {
    access_token: 'test-access-token',
    token_type: 'bearer',
    expires_in: 900,
    user: {
      id: '00000000-0000-0000-0000-000000000001',
      email: 'person@example.com',
      full_name: null,
      role,
      is_active: true,
      is_email_verified: true,
      mfa_enabled: false,
      notify_audit_complete: true,
      created_at: new Date().toISOString(),
      last_login_at: null,
    },
  }
}

describe('Login page', () => {
  beforeEach(() => {
    navigate.mockClear()
    setAccessToken(null)
  })

  it('sends a standard user to the user panel', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'POST /auth/refresh': { status: 401 },
        'POST /auth/login': { body: session('user') },
      }),
    )

    await renderWithProviders(<Login />)
    await userEvent.type(screen.getByLabelText(/email/i), 'person@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/app', { replace: true }))
  })

  it('sends an admin to the admin panel from the same form', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'POST /auth/refresh': { status: 401 },
        'POST /auth/login': { body: session('admin') },
      }),
    )

    await renderWithProviders(<Login />)
    await userEvent.type(screen.getByLabelText(/email/i), 'boss@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/admin', { replace: true }))
  })

  it('shows the server error and stays put on bad credentials', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'POST /auth/refresh': { status: 401 },
        'POST /auth/login': { status: 401, body: { detail: 'Incorrect email or password' } },
      }),
    )

    await renderWithProviders(<Login />)
    await userEvent.type(screen.getByLabelText(/email/i), 'person@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong-password-here')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect email or password/i)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('validates before hitting the network', async () => {
    const fetchSpy = mockFetch({ 'POST /auth/refresh': { status: 401 } })
    vi.stubGlobal('fetch', fetchSpy)

    await renderWithProviders(<Login />)
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText(/enter your email address/i)).toBeInTheDocument()
    const loginCalls = fetchSpy.mock.calls.filter(([url]) => String(url).includes('/auth/login'))
    expect(loginCalls).toHaveLength(0)
  })

  it('reveals the two-factor field when the server asks for a code', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'POST /auth/refresh': { status: 401 },
        'POST /auth/login': {
          status: 401,
          body: { detail: 'A two-factor authentication code is required' },
        },
      }),
    )

    await renderWithProviders(<Login />)
    await userEvent.type(screen.getByLabelText(/email/i), 'person@example.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'correct-horse-battery')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByLabelText(/authentication code/i)).toBeInTheDocument()
  })
})
