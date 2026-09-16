/**
 * Cliente HTTP del frontend.
 *
 * Convenciones:
 *   - Todas las llamadas usan credentials: "include" para que viajen
 *     las cookies httpOnly de sesión.
 *   - Las rutas son relativas (/api/v1/*). En dev, Next.js las reescribe
 *     al backend real con `next.config.ts`. En prod, Caddy/Nginx hace lo mismo.
 *   - Los errores del backend tienen la forma {detail: "..."} y se
 *     normalizan a un Error con el mensaje.
 */

const API_PREFIX = "/api/v1";

/**
 * Error HTTP tipado. El `status` permite discriminar 401 vs 429 en el login.
 */
export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}
// --------------------------------------------------------------------------- //
// Utilidades
// --------------------------------------------------------------------------- //
async function parseError(r: Response): Promise<HttpError> {
  try {
    const data = await r.json();
    if (typeof data?.detail === "string") {
      return new HttpError(r.status, data.detail);
    }
    if (Array.isArray(data?.detail)) {
      const first = data.detail[0];
      const msg = first?.msg ? `${first.msg}` : JSON.stringify(first);
      return new HttpError(r.status, msg);
    }
    return new HttpError(r.status, `HTTP ${r.status}`);
  } catch {
    return new HttpError(r.status, `HTTP ${r.status}`);
  }
}

// --------------------------------------------------------------------------- //
// Métodos base
// --------------------------------------------------------------------------- //
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!r.ok) throw await parseError(r);
  return (await r.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  if (!r.ok) throw await parseError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  if (!r.ok) throw await parseError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export async function apiPut<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "PUT",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  if (!r.ok) throw await parseError(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export async function apiDelete(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<void> {
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "DELETE",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  if (!r.ok) throw await parseError(r);
}

// --------------------------------------------------------------------------- //
// Upload multipart
// --------------------------------------------------------------------------- //
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) throw await parseError(r);
  return (await r.json()) as T;
}