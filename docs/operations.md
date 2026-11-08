# Production Operations Guide

This document covers the security, backup and monitoring features added to
PixelForensics. It is intentionally explicit about what is automated and what
still requires provider access or credentials.

---

## 1. Security model

### Authentication

- Local accounts: bcrypt password hashes, JWT HS256, token expiry from
  `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Optional Supabase Auth: the backend accepts legacy HS256 Supabase tokens and
  current RS256/ES256 tokens validated through JWKS.
- Roles are always read from the `profiles` table; the JWT role claim is not
  trusted for authorization.
- Login performs a bcrypt check even for unknown identifiers to reduce
  username/email timing disclosure.
- The frontend validates the stored token with `/api/auth/me` before showing a
  protected page and clears the session on a `401`.

### Authorization / IDOR controls

Every analysis, history, delete, signature and PDF/JSON report query filters by
the authenticated `user_id`. A non-owner receives `404`, which does not reveal
whether the record exists. The admin API requires the `ADMIN` role read from the
database.

The backend does not mount a static file server. Uploaded files are stored under
`LOCAL_STORAGE_PATH/<user_id>/<uuid>.<ext>` and are only read server-side for PDF
generation. There is no public URL for another customer's image.

### Supabase RLS

Run `supabase/migrations/0004_security_hardening.sql` after `0003`.

Important fix: the previous `profiles` policy was `FOR ALL`, which allowed a
customer to update their own row (including `role`). The new policy is
**SELECT-only**, client writes are revoked, and `password_hash` plus
`storage_path` are excluded from client-readable columns.

After running the migration, verify in the Supabase SQL editor:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public';

select schemaname, tablename, policyname, cmd, qual, with_check
from pg_policies
where schemaname in ('public', 'storage')
order by schemaname, tablename, policyname;

select id, name, public
from storage.buckets
where id = 'images';
```

Expected results:

- `rowsecurity = true` for `profiles`, `analyses`, `analysis_results`,
  `suspicious_regions`, `audit_logs`.
- Only SELECT policies for authenticated users on the application tables.
- No INSERT/UPDATE/DELETE policies for authenticated users.
- `audit_logs` has no client policy (deny-by-default).
- The `images` bucket has `public = false`.
- Storage policies compare the first folder segment with `auth.uid()`.

The FastAPI backend uses the database connection from `DATABASE_URL` (the
Postgres owner/service role), so these client-facing restrictions do not break
the API. Do not use the Supabase anon key as `DATABASE_URL`.

### Storage buckets

The current code stores uploads on the backend filesystem. If Supabase Storage is
enabled later, the migration creates a private `images` bucket with owner-folder
policies. Do not make that bucket public. Generated reports are produced on
demand and are not stored in a bucket.

---

## 2. Automated backups

### What is backed up

1. **Database**
   - SQLite: online backup through the SQLite backup API, gzip-compressed.
   - PostgreSQL/Supabase with `pg_dump` available: custom-format dump.
   - PostgreSQL/Supabase without PostgreSQL client tools: a read-only **logical
     JSONL dump** of the five application tables, gzip-compressed. Set
     `BACKUP_POSTGRES_MODE=auto` (default), `pg_dump`, or `logical`.
2. **Local uploaded images**
   - Content-addressed storage objects (`backups/storage/objects/<sha256>`).
   - A per-run manifest (`backups/storage/manifests/<id>.json`) records the
     original relative path, SHA-256 and size.
   - Unchanged files are not copied again, so daily backups do not duplicate
     large images.
3. **Backup records**
   - `backups/records/<id>.json` contains timestamp, status, duration, database
     size/hash, storage counts and a sanitized error message.

### Schedule

The backend starts a daily scheduler when `BACKUP_ENABLED=true`. It checks every
`BACKUP_CHECK_INTERVAL_MINUTES` and runs once per UTC day after
`BACKUP_HOUR_UTC` (default 02:00 UTC). A lock file prevents two jobs from
running simultaneously.

If the deployment uses multiple workers or an ephemeral filesystem, disable the
in-process scheduler and run the CLI from the platform scheduler/cron instead:

```bash
BACKUP_ENABLED=false
python tools/backup.py
```

Set `BACKUP_DIR` to a persistent private volume outside the web root. It must
not be inside `LOCAL_STORAGE_PATH`; the code rejects that configuration.

### Retention

`BACKUP_RETENTION_DAYS` (default 14) controls cleanup. The newest successful
backup is always retained. Database copies, manifests and records older than the
cutoff are removed, and storage objects are garbage-collected only when no
retained manifest references them.

### Backup record locations

- `BACKUP_DIR/records/` — per-run status records.
- `BACKUP_DIR/restores/` — restore verification records.
- `BACKUP_DIR/storage/objects/` — deduplicated image objects.
- `BACKUP_DIR/storage/manifests/` — file path/hash maps.

These directories are not served by FastAPI. They should also be excluded from
source control and made readable only by the application service account.

### Supabase managed backups

Supabase projects may provide managed backups or point-in-time recovery
depending on the plan. Those must be enabled in the Supabase dashboard; this
repository cannot verify plan capabilities. If managed backups are available,
use them for the database **and still back up the local storage directory**
separately, because database backups do not include filesystem uploads.

---

## 3. Restore verification

### Automated verification

After a successful backup, `BACKUP_VERIFY_AFTER_RUN=true` runs a restore test
into an isolated temporary workspace. It never restores over production.

Checks performed:

- SQLite `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
- Required tables exist: `profiles`, `analyses`, `analysis_results`,
  `suspicious_regions`, `audit_logs`.
- Row counts for each table.
- Sample profile and analysis rows are readable.
- No analysis has a missing owner.
- Every storage object referenced by the manifest exists and matches its
  SHA-256 hash.
- Storage files are copied into the temporary restore workspace.

Manual run:

```bash
python tools/restore_verify.py
python tools/restore_verify.py --backup 20260101T020000Z
```

### PostgreSQL restore test

A **logical** backup is restored into a temporary SQLite database and verified
automatically; no second Postgres database is required.

A **pg_dump** backup requires:

1. `RESTORE_TEST_DATABASE_URL` pointing at an isolated database.
2. The database name containing `test` or `restore`.
3. `pg_restore` and `psql` installed on the host.

The code refuses to run if the test database matches production host/database.
If the tools or test database are missing, the restore record is marked
`pending` with a reason. It is never reported as successful.

### Manual restore procedure (SQLite)

1. Stop the application or put it into maintenance mode.
2. Copy the current database aside as a precaution.
3. Decompress the chosen `db/*.sqlite.gz` file.
4. Replace the database file only after verifying the copy.
5. Run the application and check login, history and a report download.
6. Confirm the restore verification record says `success`.

Do not run this procedure against production during testing.

---

## 4. Error logging and alerts

### Structured logs

The backend writes one JSON object per line to `LOG_FILE`
(default `./logs/app.jsonl`) and to stderr. Each record contains:

- timestamp, severity, category, service and module;
- request ID (`X-Request-ID`);
- a safe message;
- recovered flag;
- sanitized technical details;
- exception traceback only in the server-side log (never in an API response).

The following are redacted: passwords, bearer tokens, JWTs, API keys, cookies,
authorization headers, database URLs with passwords, and sensitive environment
variable values.

### Error categories

`auth`, `upload`, `analysis`, `report`, `storage`, `database`, `backup`,
`restore`, `frontend`, `monitoring`, `http`, `unhandled`, `alerting`.

### Customer-facing errors

Unhandled errors return:

```json
{"detail": "Something went wrong. Please try again.", "request_id": "..."}
```

Analysis failures return a simple retry message. Database errors, stack traces
and internal paths are not returned to customers.

### Alerts

Alert delivery is configured with either:

- `ALERT_WEBHOOK_URL` (Slack, Discord or a generic JSON webhook), or
- SMTP variables (`ALERT_EMAIL_SMTP_HOST`, `ALERT_EMAIL_SMTP_PORT`,
  `ALERT_EMAIL_SMTP_USER`, `ALERT_EMAIL_SMTP_PASSWORD`, `ALERT_EMAIL_FROM`,
  `ALERT_EMAIL_TO`).

If neither is configured, alerts are recorded in `logs/alerts.jsonl` and shown
in the admin dashboard only. The system does **not** claim an external alert was
delivered until a destination is configured.

Duplicate suppression uses a fingerprint plus `ALERT_COOLDOWN_MINUTES` (default
30). The alert includes the request ID, category, occurrence count and sanitized
details.

Test alert endpoint (admin only):

```text
POST /api/admin/monitoring/test-alert
```

### Availability monitoring

- `/api/health` is a liveness probe and does not touch the database.
- `/api/ready` checks the database and storage; it returns `503` when either is
  unavailable.
- Configure an external uptime monitor to poll `/api/ready` every 1–5 minutes.
  A process cannot alert on its own total downtime, so external monitoring is
  required for that case.

The in-process monitoring loop checks the database and storage every
`MONITOR_INTERVAL_SECONDS` and alerts on a healthy → down transition, then logs
recovery.

---

## 5. Admin dashboard

The Admin Dashboard now has a **Monitoring & Backups** section showing:

- latest backup status and last success time;
- retention and schedule information;
- latest restore verification status;
- failed analyses in the last 24 hours;
- recent critical errors (timestamp, category, message, request ID);
- recent alerts and whether external delivery is configured;
- a **Run backup now** button and a **Verify restore** button.

Only an authenticated `ADMIN` can read this data. The response contains no
database credentials, absolute backup paths or customer analysis content.

---

## 6. Required manual steps

1. Run `supabase/migrations/0004_security_hardening.sql`.
2. Verify the RLS/storage queries in Section 1.
3. Set a long random `SECRET_KEY`; rotate the default demo admin password.
4. Set `BACKUP_DIR` to a persistent private volume outside the web root.
5. Install `pg_dump`/`pg_restore`/`psql` if you want a full PostgreSQL custom
   dump, or leave `BACKUP_POSTGRES_MODE=auto` to use the logical application-table
   fallback. Provider-managed database backups can be used in addition.
6. Configure `ALERT_WEBHOOK_URL` or SMTP variables, then call the test-alert
   endpoint.
7. Configure an external uptime monitor for `/api/ready`.
8. Run the restore verification and confirm the record says `success` (or
   `pending` with a clearly understood reason).