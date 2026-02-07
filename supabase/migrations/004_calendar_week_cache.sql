-- calendar_week_cache: cache week events/busy/free per user
create table if not exists public.calendar_week_cache (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  week_start timestamptz not null,
  week_end timestamptz not null,
  events jsonb not null default '[]'::jsonb,
  busy jsonb not null default '[]'::jsonb,
  free jsonb not null default '[]'::jsonb,
  fetched_at timestamptz not null default now()
);

create unique index if not exists calendar_week_cache_user_range_key
  on public.calendar_week_cache (user_id, week_start, week_end);

alter table public.calendar_week_cache enable row level security;

create policy "Users can manage own calendar_week_cache"
  on public.calendar_week_cache for all using (auth.uid() = user_id);
