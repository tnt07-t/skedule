-- user_profiles: per-user profile + preferences
create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  timezone text default 'UTC',
  preferences jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table public.user_profiles enable row level security;

create policy "Users can manage own profile"
  on public.user_profiles for all using (auth.uid() = user_id);

create index if not exists user_profiles_user_id on public.user_profiles(user_id);
