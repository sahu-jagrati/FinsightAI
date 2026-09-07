# FinSight AI — frontend

Next.js (App Router) + TypeScript + Tailwind frontend for FinSight AI.

See the [repo root README](../README.md) for the full project overview,
architecture, and setup instructions (Docker Compose brings this up
alongside the backend/Postgres/Redis).

## Local development (outside Docker)

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000. Requires the backend running at the URL set in
`NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | start the dev server (Turbopack) |
| `npm run build` | production build |
| `npm run start` | run a production build |
| `npm run lint` | ESLint |
| `npm test` | Vitest + React Testing Library |
