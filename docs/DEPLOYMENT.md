# PixelForensics — Deployment Guide

This guide explains how to deploy the existing PixelForensics project:

- **Frontend:** Vercel (React + Vite)
- **Backend:** Render (Python FastAPI)
- **Database / Authentication / Storage:** Supabase (PostgreSQL, Auth, Storage)

No real secrets are stored in this repository. Real values must be entered only in the
hosting dashboards / environment variable editors.

---

## 1. Architecture

```
Browser (Vercel frontend)
   │  HTTPS
   ├──────────────▶ Backend API (Render)  ───▶ Supabase PostgreSQL (auth + data)
   │                                      ───▶ Supabase Auth (JWT issuing)
   │                                      ───▶ Supabase Storage (bucket: images)
```

- Frontend calls the backend API via `VITE_API_BASE_URL`.
- Backend validates Supabase JWTs (ES256 via JWKS / HS256 legacy) and issues local JWTs.
- Backend stores uploaded images under `LOCAL_STORAGE_PATH` (local filesystem by default) or Supabase Storage bucket `images` when `STORAGE_MODE=supabase`.

---

## 2. Deploying the Frontend on Vercel

1. Go to https://vercel.com and import the GitHub repository `vamshikrishna2006/PixelForensics`.
2. **Root Directory:** `frontend`
3. **Framework Preset:** `Vite`
4. **Build Command:** `npm run build`
5. **Output Directory:** `dist`
6. **Install Command:** `npm install`
7. **Environment Variables (Production):**

   | Variable | Value |
   |---|---|
   | `VITE_API_BASE_URL` | Render backend public URL, e.g. `https://<your-backend>.onrender.com` |
   | `VITE_SUPABASE_URL` | Supabase project URL, e.g. `https://<project>.supabase.co` |
   | `VITE_SUPABASE_ANON_KEY` | Supabase anonymous public key (safe to expose) |

8. Deploy. The SPA fallback is configured via `frontend/vercel.json` (`rewrites` → `/index.html`).

---

## 3. Deploying the Backend on Render

1. In Render, create a **Web Service** from the same GitHub repository.
2. **Root Directory:** `backend`
3. **Runtime:** Python 3.11 (Dockerfile available: `backend/Dockerfile`, or native runtime).
4. **Build Command:** `pip install -r requirements.txt` *(if not using Docker)*
5. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - The Dockerfile now also uses `${PORT:-8000}` so the container binds to the port
     injected by Render (`$PORT`).
6. **Health Check Path:** `/api/health`
7. **Environment Variables (Render) — required:**

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Supabase PostgreSQL (session pooler, port `5432`) |
   | `SUPABASE_URL` | Supabase project URL |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (backend only) |
   | `SUPABASE_ANON_KEY` | Supabase anon key (backend) |
   | `SUPABASE_STORAGE_BUCKET` | Storage bucket name, e.g. `images` |
   | `SECRET_KEY` | Long random string (backend) |
   | `JWT_ALGORITHM` | `HS256` |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` |
   | `CORS_ORIGINS` | Vercel frontend URL(s), e.g. `https://<app>.vercel.app,https://localhost:5173` |
   | `RATE_LIMIT_PER_MINUTE` | `60` |
   | `MAX_UPLOAD_SIZE_MB` | `10` |
   | `ALLOWED_MIME_TYPES` | `image/jpeg,image/png,image/webp` |
   | `LOCAL_STORAGE_PATH` | Local storage path (default `./storage`) |
   | `ANALYSIS_CONCURRENCY` | Max concurrent analyses (default `1` for 512 MB Render) |
   | `MAX_IMAGE_DIMENSION` | Max pixels on a side before reject (default `4096`) |
   | `MAX_PIXEL_COUNT` | Max total pixels (default `8388608` ≈ 8 MP) |
   | `STORAGE_MODE` | `local` / `supabase` / `hybrid` (default `local`) |
   | `SUPABASE_STORAGE_ENABLED` | `true` / `false` (enable Supabase Storage uploads) |
   | `MONITORING_ENABLED` | `true` / `false` |
   | `BACKUP_ENABLED` | `true` / `false` |
   | `DEFAULT_ADMIN_EMAIL` | Admin login email |
   | `DEFAULT_ADMIN_PASSWORD` | Admin login password |
   | `DEFAULT_ADMIN_USERNAME` | Admin username |

---

## 4. Supabase Manual Steps

1. Open the Supabase dashboard → **Authentication → URL Configuration**:
   - Add the Render backend URL and the Vercel frontend URL as allowed redirect URLs / site URL.
2. Database migrations: run `supabase/migrations/0001_init.sql` … `0004_security_hardening.sql`
   (SQL editor or `supabase db push`). Do **not** run destructive changes blindly.
3. Storage: ensure bucket (e.g. `images`) exists and is used by the backend.
4. RLS: policies are included in migrations; verify customer isolation after applying.

---

## 5. Verification Checklist

- Frontend: production build passes; API base URL points to Render backend.
- Backend: `GET /api/health` → `200 {"status":"ok"}`; `GET /api/ready` → ready when DB/storage OK.
- Auth: customer/admin login flows; role-based access.
- Analysis: upload → ML pipeline → PDF/JSON report → download.

---

## 6. Deployment Order

1. Deploy backend on Render (with env vars).
2. Deploy frontend on Vercel (with env vars pointing to backend).
3. Configure Supabase (env + migrations + storage).
4. Verify: health checks, login, analysis, reports.

---

## 7. Remaining Notes

- Render free-tier filesystem is ephemeral → local image storage may not persist; use external storage for production persistence.
- No trained model files are required — the app uses classical image-forensics algorithms.
