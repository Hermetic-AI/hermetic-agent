// Thin fetch wrapper around the backend HTTP API.
//
// Goals:
// - Prepend the configured base URL (VITE_API_BASE_URL or /api proxy).
// - Parse JSON, normalise error responses to a typed `ApiError`.
// - Support AbortController for cancellation.

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

export async function request<T = unknown>({
  path,
  body,
  query,
  baseUrl = config.apiBaseUrl,
  headers,
  ...init
}: RequestOptions): Promise<T> {
  const url = buildUrl(baseUrl, path, query);

  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    // 读取"最新"的 CRM token, 不是模块加载时的快照.
    // 用户在设置面板修改 token 后, 下一次请求立刻生效.
    ...(config.getCrmToken() ? { 'X-CRM-Token': config.getCrmToken() } : {}),
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
