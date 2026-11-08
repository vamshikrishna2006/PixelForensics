# Architecture

Monorepo: `frontend/` (React+TS+Vite), `backend/` (FastAPI), `supabase/` (Postgres+RLS).

Request flow: Browser -> FastAPI (`/api/*`, JWT in Authorization header) -> forensic pipeline -> SQLite (local) / Supabase Postgres (prod) -> JSON/PDF report.

Key decisions: classical DIP only (no CNNs); roles enforced server-side from DB/JWT; per-user storage isolation (`user_id/uuid.ext`); RLS mirrors API isolation.
