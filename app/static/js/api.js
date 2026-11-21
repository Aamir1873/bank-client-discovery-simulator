// Fetch wrappers for the server's API. Every failure becomes an ApiError with a plain message.
import { W } from './words.js';

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

async function call(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(W.errors.network);
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty or not JSON */ }
  if (!res.ok) {
    const msg = (data && data.error) || (res.status === 404 ? W.errors.notFound : W.errors.generic);
    throw new ApiError(msg, res.status);
  }
  return data;
}

let catalogueCache = null;

export const api = {
  clients: () => call('/api/clients'),
  client: (id) => call(`/api/clients/${encodeURIComponent(id)}`),
  products: () => call('/api/products'),
  /** The catalogue, fetched once and shared by every view. */
  catalogue: async () => (catalogueCache ||= await call('/api/products')),
  startInterview: (clientId) => call('/api/interviews', { method: 'POST', body: { client_id: clientId } }),
  send: (iid, text) => call(`/api/interviews/${iid}/messages`, { method: 'POST', body: { text } }),
  hint: (iid) => call(`/api/interviews/${iid}/hint`, { method: 'POST' }),
  feedback: (iid, summary, picks) => call(`/api/interviews/${iid}/feedback`, { method: 'POST', body: { summary, picks } }),
  exportUrl: (iid) => `/api/interviews/${iid}/export`,
};
