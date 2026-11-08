-- PixelForensics Option B migration: link profiles to Supabase Auth.
-- Run AFTER 0001_init.sql in Supabase SQL editor.
-- Safe: keeps existing local-UUID rows, allows Supabase auth.users UUIDs.

-- 1) profiles.id references auth.users when present (nullable FK not enforced for local rows)
-- Drop password_hash requirement for Supabase users
alter table profiles alter column password_hash drop not null;

-- 2) Auto-create profile on new Supabase signup (collision-safe, username unique)
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare base_username text; try_username text;
begin
  base_username := regexp_replace(split_part(coalesce(new.email,''), '@', 1), '[^a-zA-Z0-9_.-]', '', 'g');
  if base_username is null or base_username = '' or length(base_username) < 3 then
    base_username := 'user_' || substr(new.id::text,1,8);
  end if;
  try_username := substr(base_username,1,28) || '_' || substr(new.id::text,1,4);
  for i in 1..5 loop
    begin
      insert into public.profiles (id, username, email, password_hash, role, status)
      values (new.id::text, try_username,
              coalesce(new.email, new.id::text || '@supabase.local'),
              'supabase-auth', 'CUSTOMER', 'active')
      on conflict (id) do nothing;
      return new;
    exception when unique_violation then
      try_username := substr(base_username,1,24) || '_' || substr(md5(random()::text),1,6);
    end;
  end loop;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users for each row execute function public.handle_new_user();