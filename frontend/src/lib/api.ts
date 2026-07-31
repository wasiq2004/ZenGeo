/**
 * API client.
 *
 * The access token lives in a module variable, never in localStorage - anything
 * readable by JavaScript is readable by an XSS payload. The long-lived refresh
 * token is an httpOnly cookie the browser attaches automatically, so the SPA
 * never sees it.
 *
 * On a 401 the client transparently refreshes once and replays the request.
 * Concurrent 401s share a single refresh (`refreshPromise`) so a dashboard that
 * fires six queries at once does not trigger six rotations - which the reuse
 * detector would treat as token theft.
 */
import { readCookie } from './utils'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const CSRF_COOKIE = 'geo_csrf'
const CSRF_HEADER = 'X-CSRF-Token'

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null
let onAuthLost: (() => void) | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function getAccessToken() {
  return accessToken
}

/** Registered by AuthProvider so an unrecoverable 401 clears app state. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onAuthLost = handler
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: unknown,
    readonly requestId?: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Field-level validation errors from FastAPI, keyed by field name. */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {}
    if (Array.isArray(this.detail)) {
      for (const item of this.detail as Array<{ loc?: unknown[]; msg?: string }>) {
        const field = item.loc?.slice(1).join('.') ?? '_'
        if (item.msg) out[field] = item.msg
      }
    }
    return out
  }
}

function messageFrom(payload: unknown, status: number): string {
  if (typeof payload === 'string' && payload) return payload
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined
      if (first?.msg) {
        const field = first.loc?.slice(1).join('.')
        return field ? `${field}: ${first.msg}` : first.msg
      }
    }
  }
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status >= 500) return 'Something went wrong on our side. Please try again.'
  return `Request failed (${status})`
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null
  const type = response.headers.get('content-type') ?? ''
  if (type.includes('application/json')) {
    return response.json().catch(() => null)
  }
  return response.text().catch(() => null)
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Skip the automatic refresh-and-replay (used by the refresh call itself). */
  skipAuthRetry?: boolean
  /** Attach the CSRF header (needed for cookie-authenticated endpoints). */
  withCsrf?: boolean
}

async function rawRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const { body, withCsrf, skipAuthRetry: _skip, headers, ...rest } = options
  const finalHeaders = new Headers(headers)

  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders.set('Content-Type', 'application/json')
  }
  if (accessToken) {
    finalHeaders.set('Authorization', `Bearer ${accessToken}`)
  }
  if (withCsrf) {
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) finalHeaders.set(CSRF_HEADER, csrf)
  }

  return fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: finalHeaders,
    // Always send cookies: the refresh cookie is how a session survives reload.
    credentials: 'include',
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  })
}

/** Refresh the access token. Returns true on success. De-duplicated. */
export function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const response = await rawRequest('/auth/refresh', {
          method: 'POST',
          withCsrf: true,
          skipAuthRetry: true,
        })
        if (!response.ok) return false
        const data = (await response.json()) as { access_token?: string }
        if (!data.access_token) return false
        accessToken = data.access_token
        return true
      } catch {
        return false
      } finally {
        // Cleared on the next tick so callers awaiting this promise all resolve
        // against the same result before a new refresh can start.
        setTimeout(() => {
          refreshPromise = null
        }, 0)
      }
    })()
  }
  return refreshPromise
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await rawRequest(path, options)

  if (response.status === 401 && !options.skipAuthRetry) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      response = await rawRequest(path, { ...options, skipAuthRetry: true })
    } else {
      accessToken = null
      onAuthLost?.()
    }
  }

  const payload = await parseBody(response)

  if (!response.ok) {
    throw new ApiError(
      response.status,
      messageFrom(payload, response.status),
      (payload as { detail?: unknown })?.detail,
      response.headers.get('X-Request-ID'),
    )
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'DELETE' }),
}

/** Fetch a protected binary file (the PDF report) as a blob. */
export async function apiDownload(path: string): Promise<Blob> {
  let response = await rawRequest(path, { method: 'GET' })
  if (response.status === 401) {
    if (await refreshAccessToken()) {
      response = await rawRequest(path, { method: 'GET', skipAuthRetry: true })
    }
  }
  if (!response.ok) {
    const payload = await parseBody(response)
    throw new ApiError(response.status, messageFrom(payload, response.status))
  }
  return response.blob()
}
