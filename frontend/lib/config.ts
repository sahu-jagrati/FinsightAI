// Central place for reading public runtime config. Only NEXT_PUBLIC_*
// variables are available in the browser bundle (Section 27 — no secrets
// here). Server components/route handlers may read non-public env vars
// directly from process.env instead.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
