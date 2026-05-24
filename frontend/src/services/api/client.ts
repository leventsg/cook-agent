/**
 * Base API client with common utilities
 */

import { API_BASE, STORAGE_KEYS } from '../../constants';
import { capitalize } from '../../utils';

/**
 * Create authorization headers
 */
export function createAuthHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined;
}

/**
 * Create headers with content-type and optional auth
 */
export function createJsonHeaders(token?: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/**
 * Custom error for 401 Unauthorized responses
 */
export class UnauthorizedError extends Error {
  constructor(message: string = 'Unauthorized') {
    super(message);
    this.name = 'UnauthorizedError';
  }
}

/**
 * Parse typical FastAPI error responses (Pydantic validation errors or HTTPException)
 * and return a friendly message string.
 */
export async function parseErrorResponse(response: Response): Promise<string> {
  // Handle 401 Unauthorized - clear auth data
  if (response.status === 401) {
    localStorage.removeItem(STORAGE_KEYS.TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USERNAME);
    // Dispatch custom event to notify auth context
    window.dispatchEvent(new Event('auth-unauthorized'));
    throw new UnauthorizedError();
  }

  const contentType = response.headers.get('content-type') || '';
  
  try {
    if (contentType.includes('application/json')) {
      const body = await response.json();

      // Pydantic validation errors use `detail` as an array of error objects
      if (Array.isArray(body.detail)) {
        const parts = body.detail.map((err: { loc?: string[]; msg: string; ctx?: Record<string, unknown> }) => {
          const loc = Array.isArray(err.loc) ? err.loc.filter(Boolean) : [];
          const field = loc.length ? loc[loc.length - 1] : 'field';
          const msg = typeof err.msg === 'string' ? err.msg : JSON.stringify(err.msg);
          return `${capitalize(String(field))}: ${friendlyMessageFor(msg, err.ctx)}`.trim();
        });
        return parts.join('\n');
      }

      // If detail is a string, return it
      if (typeof body.detail === 'string') {
        return body.detail;
      }

      // Fallback to message or stringified body
      if (body.message) return String(body.message);
      return JSON.stringify(body);
    }
    
    // Not JSON; return raw text
    return await response.text();
  } catch (e) {
    return String(e instanceof Error ? e.message : 'Unknown error');
  }
}

/**
 * Convert error messages to user-friendly format
 */
function friendlyMessageFor(msg: string, ctx?: Record<string, unknown>): string {
  if (msg.includes('at least') && ctx && ctx.min_length) {
    return `Must be at least ${ctx.min_length} characters`;
  }
  if (msg.includes('field required') || msg === 'value_error.missing') {
    return 'This field is required';
  }
  return msg;
}

/**
 * Make a GET request
 */
export async function apiGet<T>(endpoint: string, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Make a POST request
 */
export async function apiPost<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: createJsonHeaders(token),
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Make a PUT request
 */
export async function apiPut<T, D = unknown>(
  endpoint: string,
  data: D,
  token?: string
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'PUT',
    headers: createJsonHeaders(token),
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Make a DELETE request
 */
export async function apiDelete<T>(endpoint: string, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'DELETE',
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}
