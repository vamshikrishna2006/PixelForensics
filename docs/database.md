# Database

Tables: profiles, analyses, analysis_results (full_json), suspicious_regions, audit_logs. See `supabase/migrations/0001_init.sql`.
Local dev: SQLite file `pixelforensics.db` via aiosqlite; prod: Supabase Postgres (DATABASE_URL).
