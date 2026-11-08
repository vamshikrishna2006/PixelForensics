-- PixelForensics production security hardening (run after 0003).
--
-- Why this migration exists
-- -------------------------
-- The previous "own profile" policy was FOR ALL, which allowed a customer to
-- UPDATE their own profiles row through PostgREST -- including the `role`
-- column.  That is a privilege-escalation path.  The backend still owns every
-- write, so direct client writes are no longer needed.
--
-- Result:
--   * authenticated users can SELECT only their own rows;
--   * no client INSERT/UPDATE/DELETE policies remain on application tables;
--   * password hashes and internal storage paths are not exposed to the
--     Supabase client roles;
--   * audit logs are deny-by-default;
--   * the optional private "images" bucket is owner-folder isolated.
--
-- The FastAPI backend connects directly with the database owner/service role
-- and is therefore unaffected by these client-facing policies.

begin;

-- ------------------------------------------------------------------ tables
alter table public.profiles           enable row level security;
alter table public.analyses           enable row level security;
alter table public.analysis_results   enable row level security;
alter table public.suspicious_regions enable row level security;
alter table public.audit_logs         enable row level security;

-- Remove the old FOR ALL policies (read + write).
drop policy if exists "own profile" on public.profiles;
drop policy if exists "own analyses" on public.analyses;
drop policy if exists "own results" on public.analysis_results;
drop policy if exists "own regions" on public.suspicious_regions;

-- Read-only, owner-scoped policies.
drop policy if exists "pf read own profile" on public.profiles;
create policy "pf read own profile" on public.profiles
  for select to authenticated
  using (auth.uid()::text = id);

drop policy if exists "pf read own analyses" on public.analyses;
create policy "pf read own analyses" on public.analyses
  for select to authenticated
  using (auth.uid()::text = user_id);

drop policy if exists "pf read own results" on public.analysis_results;
create policy "pf read own results" on public.analysis_results
  for select to authenticated
  using (
    exists (
      select 1 from public.analyses a
      where a.id = analysis_id and a.user_id = auth.uid()::text
    )
  );

drop policy if exists "pf read own regions" on public.suspicious_regions;
create policy "pf read own regions" on public.suspicious_regions
  for select to authenticated
  using (
    exists (
      select 1 from public.analyses a
      where a.id = analysis_id and a.user_id = auth.uid()::text
    )
  );

-- Audit logs: RLS is enabled and no client policy exists.  Revoke table
-- privileges explicitly so the deny is unambiguous.
revoke all on public.audit_logs from anon, authenticated;

-- No client-side writes anywhere in the application schema.
revoke insert, update, delete on public.profiles           from anon, authenticated;
revoke insert, update, delete on public.analyses           from anon, authenticated;
revoke insert, update, delete on public.analysis_results   from anon, authenticated;
revoke insert, update, delete on public.suspicious_regions from anon, authenticated;

-- Restrict readable columns.  In particular, never expose password_hash or
-- the server-side storage_path to client roles.
revoke select on public.profiles from anon, authenticated;
grant select (id, username, email, role, status, created_at, updated_at)
  on public.profiles to authenticated;

revoke select on public.analyses from anon, authenticated;
grant select (id, user_id, filename, mime, size_bytes, status, verdict,
              confidence, final_score, processing_time_s, created_at, completed_at)
  on public.analyses to authenticated;

revoke select on public.analysis_results from anon, authenticated;
grant select (id, analysis_id, full_json)
  on public.analysis_results to authenticated;

revoke select on public.suspicious_regions from anon, authenticated;
grant select (id, analysis_id, x, y, width, height, reason)
  on public.suspicious_regions to authenticated;

-- --------------------------------------------------------------- storage
-- The application currently stores uploads on the backend filesystem, but the
-- optional Supabase Storage bucket must still be private if it is enabled.
insert into storage.buckets (id, name, public)
values ('images', 'images', false)
on conflict (id) do update set public = false;

drop policy if exists "pf images own read"   on storage.objects;
drop policy if exists "pf images own insert" on storage.objects;
drop policy if exists "pf images own update" on storage.objects;
drop policy if exists "pf images own delete" on storage.objects;

create policy "pf images own read" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "pf images own insert" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "pf images own update" on storage.objects
  for update to authenticated
  using (
    bucket_id = 'images'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "pf images own delete" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

commit;

-- Verification (run manually in the Supabase SQL editor):
--   select tablename, rowsecurity from pg_tables where schemaname = 'public';
--   select schemaname, tablename, policyname, cmd, qual, with_check
--     from pg_policies where schemaname in ('public','storage')
--     order by schemaname, tablename, policyname;
--   select id, name, public from storage.buckets where id = 'images';