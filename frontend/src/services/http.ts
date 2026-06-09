// Thin fetch wrapper around the backend HTTP API.
//
// Goals:
// - Prepend the configured base URL (VITE_API_BASE_URL or /api proxy).
// - Parse JSON, normalise error responses to a typed `ApiError`.
// - Support AbortController for cancellation.
//
// Token injection:
// - `registerTokenGetter(getter)` lets AuthContext register a function
//   that returns the current login token.  Every request then forwards it
//   as `X-MCP-Token` (Hub `_extract_mcp_token` reads this header).
// - Falls back to `X-CRM-Token` from the legacy settings panel path.
// - A `Authorization: Bearer <token>` is also added so backend OAuth
//   parsers can use it as a last-resort option.

import { config } from '../config';

export class ApiError extends Error {
  readonly status: number;
  readonly body?: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

interface RequestOptions extends Omit<RequestInit, 'body' | 'signal'> {
  body?: unknown;
  signal?: AbortSignal;
  /** Override the base URL prefix.  Defaults to `config.apiBaseUrl`. */
  baseUrl?: string;
  /** Path joined to the base.  Leading slash optional. */
  path: string;
  /** Query string params, encoded into the URL. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /**
   * Skip token injection for this request.  Used for the auth endpoints
   * themselves (logon / captcha), where sending an unrelated token would
   * be misleading.
   */
  skipAuth?: boolean;
}

function buildUrl(baseUrl: string, path: string, query?: RequestOptions['query']): string {
  const base = baseUrl.replace(/\/+$/, '');
  const normalisedPath = path.startsWith('/') ? path : `/${path}`;
  let url = `${base}${normalisedPath}`;
  if (query) {
    const qs = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(
        ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`,
      )
      .join('&');
    if (qs) url += `?${qs}`;
  }
  return url;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

async function parseBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  // Fall back to text so callers can still surface it.
  try {
    return await res.text();
  } catch {
    return null;
  }
}

function extractErrorMessage(body: unknown, status: number): string {
  if (isPlainObject(body) && typeof body.error === 'string') {
    return body.error;
  }
  if (typeof body === 'string' && body.length > 0) {
    return body;
  }
  return `Request failed (HTTP ${status})`;
}

// ---------------------------------------------------------------------------
// Token injection
// ---------------------------------------------------------------------------

type TokenGetter = () => string | null | undefined;

let _tokenGetter: TokenGetter | null = null;

/**
 * Register a function that returns the current login token.
 *
 * Called once at app startup (by AuthContext wiring).  The getter is
 * invoked on every request, so token changes (login / logout) take
 * effect immediately without re-binding the fetch wrapper.
 */
export function registerTokenGetter(getter: TokenGetter | null): void {
  _tokenGetter = getter;
}

/**
 * Resolve the current login token (read-only convenience for callers
 * that bypass `http`, e.g. SSE streams and direct fetch in chat service).
 * Returns an empty string when not authenticated.
 */
export function resolveAuthToken(): string {
  if (_tokenGetter) {
    const t = _tokenGetter();
    if (t) return t;
  }
  return config.getCrmToken();
}

function buildAuthHeaders(): Record<string, string> {
  const token = resolveAuthToken();
  if (!token) return {};
  return {
    // 优先 X-MCP-Token — Hub `_extract_mcp_token` 第一个读的就是这个.
    'X-MCP-Token': token,
    // 兜底 Authorization Bearer, 给 OAuth 风格的中间件 (e.g. nginx auth_request)
    Authorization: `Bearer ${token}`,
  };
}

export async function request<T = unknown>({
  path,
  body,
  query,
  baseUrl = config.apiBaseUrl,
  headers,
  skipAuth = false,
  ...init
}: RequestOptions): Promise<T> {
  const url = buildUrl(baseUrl, path, query);

  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(skipAuth ? {} : buildAuthHeaders()),
    ...(headers as Record<string, string> | undefined),
  };
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      method: init.method ?? (body !== undefined ? 'POST' : 'GET'),
      headers: finalHeaders,
      body: payload,
      signal: init.signal,
      credentials: 'omit',
    });
  } catch (e) {
    // Network / abort errors.
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new ApiError('Request aborted', 0, null);
    }
    throw new ApiError(
      e instanceof Error ? e.message : 'Network error',
      0,
      null,
    );
  }

  const parsed = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(extractErrorMessage(parsed, res.status), res.status, parsed);
  }
  return parsed as T;
}

export const http = {
  get: <T>(path: string, opts: Omit<RequestOptions, 'path' | 'body' | 'method'> = {}) =>
    request<T>({ ...opts, path, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'path' | 'body' | 'method'> = {}) =>
    request<T>({ ...opts, path, body, method: 'POST' }),
  put: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'path' | 'body' | 'method'> = {}) =>
    request<T>({ ...opts, path, body, method: 'PUT' }),
  patch: <T>(path: string, body?: unknown, opts: Omit<RequestOptions, 'path' | 'body' | 'method'> = {}) =>
    request<T>({ ...opts, path, body, method: 'PATCH' }),
  delete: <T>(path: string, opts: Omit<RequestOptions, 'path' | 'body' | 'method'> = {}) =>
    request<T>({ ...opts, path, method: 'DELETE' }),
};
