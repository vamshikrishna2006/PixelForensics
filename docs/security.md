# Security

- Passwords: bcrypt via passlib; never logged.
- JWT (HS256) carries sub+role; `current_user` re-reads role/status from DB per request; `admin_user` gates admin routes (403 otherwise).
- Uploads: size cap, magic-byte sniff + extension match + real decode, UUID storage names under `user_id/`.
- Isolation: every analysis query filters `user_id == current user`; RLS mirrors this in Postgres.
- Rate limiting: slowapi per-IP; CORS restricted; secure headers (nosniff, DENY framing).
- GPS coordinates never rendered; metadata shown as supporting evidence with forgery warning.
