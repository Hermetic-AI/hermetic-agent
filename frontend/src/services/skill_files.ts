const BASE = '/agent/skills';

export interface SkillFileEntry {
  path: string;
  size: number;
  etag: string;
  modified_at: string;
}

export interface SkillFileListResult {
  code: string;
  total: number;
  items: SkillFileEntry[];
}

export interface SkillFileDownloadResult {
  code: string;
  path: string;
  content_b64: string;
}

export interface SkillFileUploadResult {
  code: string;
  path: string;
  size: number;
  etag: string;
}

export interface SkillFileDeleteResult {
  success: boolean;
  code: string;
  path: string;
}

export interface SkillFileBatchInput {
  path: string;
  content_b64: string;
}

export interface SkillFileBatchResult {
  code: string;
  results: Array<
    | { path: string; ok: true; size: number; etag: string }
    | { path: string; ok: false; error: string }
  >;
}

async function httpJson<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(`${r.status} ${r.statusText}: ${err.error ?? ''}`);
  }
  return r.json() as Promise<T>;
}

async function httpBinary(method: string, url: string, body: Blob | ArrayBuffer): Promise<Response> {
  return fetch(url, { method, body });
}

export const skillFilesApi = {
  list: (code: string) =>
    httpJson<SkillFileListResult>('GET', `${BASE}/${encodeURIComponent(code)}/files`),

  async download(code: string, path: string): Promise<Blob> {
    const r = await fetch(
      `${BASE}/${encodeURIComponent(code)}/files/${path}`,
    );
    if (!r.ok) {
      throw new Error(`${r.status} ${r.statusText}`);
    }
    const data = (await r.json()) as SkillFileDownloadResult;
    const bin = atob(data.content_b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes]);
  },

  upload: (code: string, path: string, body: Blob | ArrayBuffer) =>
    httpBinary('PUT', `${BASE}/${encodeURIComponent(code)}/files/${path}`, body)
      .then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          throw new Error(`${r.status} ${r.statusText}: ${err.error ?? ''}`);
        }
        return (await r.json()) as SkillFileUploadResult;
      }),

  delete: (code: string, path: string) =>
    httpJson<SkillFileDeleteResult>(
      'DELETE',
      `${BASE}/${encodeURIComponent(code)}/files/${path}`,
    ),

  batchUpload: (code: string, files: SkillFileBatchInput[]) =>
    httpJson<SkillFileBatchResult>(
      'POST',
      `${BASE}/${encodeURIComponent(code)}/files/batch`,
      { files },
    ),
};