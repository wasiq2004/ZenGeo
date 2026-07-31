import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, type RenderOptions, type RenderResult } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/misc'
import { ToastProvider } from '@/components/ui/toast'
import { AuthProvider } from '@/lib/auth'

function testQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

export function AllProviders({
  children,
  route = '/',
}: {
  children: ReactNode
  route?: string
}) {
  return (
    <MemoryRouter initialEntries={[route]}>
      <QueryClientProvider client={testQueryClient()}>
        <AuthProvider>
          <TooltipProvider>
            <ToastProvider>{children}</ToastProvider>
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

/**
 * Render inside every app provider.
 *
 * Async because `AuthProvider` attempts a silent token refresh on mount. Doing
 * the render and letting that settle inside one `act()` keeps React from
 * warning about state updates escaping the test, and means assertions run
 * against a settled auth state rather than a mid-bootstrap one.
 */
export async function renderWithProviders(
  ui: ReactElement,
  { route = '/', ...options }: RenderOptions & { route?: string } = {},
): Promise<RenderResult> {
  let result!: RenderResult
  await act(async () => {
    result = render(ui, {
      wrapper: ({ children }) => <AllProviders route={route}>{children}</AllProviders>,
      ...options,
    })
    // Let the boot-time refresh promise resolve before act() closes.
    await Promise.resolve()
  })
  return result
}

/** Stub `fetch` with a route table: { 'POST /auth/login': {status, body} }. */
export function mockFetch(routes: Record<string, { status?: number; body?: unknown }>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.replace(/^.*\/api\/v1/, '')
    const match = routes[`${method} ${path}`] ?? routes[path]

    if (!match) {
      return new Response(JSON.stringify({ detail: 'Not stubbed' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      })
    }
    return new Response(JSON.stringify(match.body ?? {}), {
      status: match.status ?? 200,
      headers: { 'content-type': 'application/json' },
    })
  })
}

export * from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
