-- PixelForensics Option B: rebuild public tables as TEXT ids to match backend models.py.
-- Run in Supabase SQL editor. Drops old UUID tables (data loss on live — dev only).
-- Also cleans stale auth user so email can re-register.
drop policy if exists "own profile" on profiles;
drop policy if exists "own analyses" on analyses;
drop policy if exists "own results" on analysis_results;
drop policy if exists "own regions" on suspicious_regions;
drop trigger if exists on_auth_user_created on auth.users;
drop function if exists public.handle_new_user();
drop table if exists suspicious_regions cascade;
drop table if exists analysis_results cascade;
drop table if exists analyses cascade;
drop table if exists audit_logs cascade;
drop table if exists profiles cascade;

create table profiles (
  id text primary key,
  username text unique not null,
  email text unique not null,
  password_hash text,
  role text not null default 'CUSTOMER' check (role in ('CUSTOMER','ADMIN')),
  status text not null default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table analyses (
  id text primary key,
  user_id text not null references profiles(id) on delete cascade,
  filename text not null,
  storage_path text not null,
  mime text default 'image/jpeg',
  size_bytes integer default 0,
  status text default 'completed',
  verdict text default 'INCONCLUSIVE',
  confidence double precision default 0,
  final_score double precision default 0.5,
  processing_time_s double precision default 0,
  created_at timestamptz default now(),
  completed_at timestamptz default now()
);
create index idx_analyses_user on analyses(user_id, created_at desc);

create table analysis_results (
  id text primary key,
  analysis_id text unique not null references analyses(id) on delete cascade,
  full_json jsonb not null
);

create table suspicious_regions (
  id text primary key,
  analysis_id text not null references analyses(id) on delete cascade,
  x integer not null, y integer not null,
  width integer not null, height integer not null,
  reason text default ''
);
create index idx_regions_analysis on suspicious_regions(analysis_id);

create table audit_logs (
  id text primary key,
  user_id text references profiles(id) on delete set null,
  action text not null,
  detail text default '',
  created_at timestamptz default now()
);

alter table profiles enable row level security;
alter table analyses enable row level security;
alter table analysis_results enable row level security;
alter table suspicious_regions enable row level security;
alter table audit_logs enable row level security;

create policy "own profile" on profiles for all using (auth.uid()::text = id);
create policy "own analyses" on analyses for all using (auth.uid()::text = user_id);
create policy "own results" on analysis_results for all using (
  exists (select 1 from analyses a where a.id = analysis_id and a.user_id = auth.uid()::text)
);
create policy "own regions" on suspicious_regions for all using (
  exists (select 1 from analyses a where a.id = analysis_id and a.user_id = auth.uid()::text)
);