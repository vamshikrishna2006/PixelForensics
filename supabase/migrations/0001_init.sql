-- PixelForensics initial schema (Supabase Postgres) with RLS.
create extension if not exists "pgcrypto";

create table if not exists profiles (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  email text unique not null,
  password_hash text not null,
  role text not null default 'CUSTOMER' check (role in ('CUSTOMER','ADMIN')),
  status text not null default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references profiles(id) on delete cascade,
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
create index if not exists idx_analyses_user on analyses(user_id, created_at desc);

create table if not exists analysis_results (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid unique not null references analyses(id) on delete cascade,
  full_json jsonb not null
);

create table if not exists suspicious_regions (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references analyses(id) on delete cascade,
  x integer not null, y integer not null,
  width integer not null, height integer not null,
  reason text default ''
);
create index if not exists idx_regions_analysis on suspicious_regions(analysis_id);

create table if not exists audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id) on delete set null,
  action text not null,
  detail text default '',
  created_at timestamptz default now()
);

alter table profiles enable row level security;
alter table analyses enable row level security;
alter table analysis_results enable row level security;
alter table suspicious_regions enable row level security;
alter table audit_logs enable row level security;

-- Customers see only their own rows. Service-role backend bypasses RLS.
drop policy if exists "own profile" on profiles;
create policy "own profile" on profiles for all using (auth.uid() = id);

drop policy if exists "own analyses" on analyses;
create policy "own analyses" on analyses for all using (auth.uid() = user_id);

drop policy if exists "own results" on analysis_results;
create policy "own results" on analysis_results for all using (
  exists (select 1 from analyses a where a.id = analysis_id and a.user_id = auth.uid())
);

drop policy if exists "own regions" on suspicious_regions;
create policy "own regions" on suspicious_regions for all using (
  exists (select 1 from analyses a where a.id = analysis_id and a.user_id = auth.uid())
);

-- Storage: private bucket "images" with per-user folders (user_id/...)
-- Create bucket via dashboard; policies:
-- insert/select/delete where storage.objects name starts with auth.uid()::text || '/'
