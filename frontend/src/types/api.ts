// Generic API helpers and shared response types.
//
// The backend (`openagent/api/routes.py`) uses a flat response shape:
//   { success: boolean, ...payload }
// Errors come back as:
//   { success: false, error: string }
//   or as non-2xx HTTP responses with a JSON body.

export interface ApiSuccess<T> {
  success: true;
  data?: T;
}

export interface ApiFailure {
  success: false;
  error: string;
  status?: number;
  traceback?: string;
}

export type ApiEnvelope<T> = (ApiSuccess<T> & T) | ApiFailure;

// `ApiResponse<T>` is the loose envelope returned by the backend.
// Many endpoints return their payload *flat* (i.e. spread at the top level),
// so we model it as `Partial<{ success, error }> & T`.
export type ApiResponse<T> = Partial<{ success: boolean; error: string }> & T;

export interface PageParams {
  page: number;
  pageSize: number;
}

export interface PageResult<T> {
  list: T[];
  total: number;
  page: number;
  pageSize: number;
}
