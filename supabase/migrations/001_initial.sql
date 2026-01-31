-- calendar_tokens: store Google Calendar OAuth tokens per user (linked to auth.users)
create table if not exists public.calendar_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  refresh_token text,
  access_token text,
  token_expiry timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- tasks: user-created tasks with preferences
create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text default '',
  difficulty text not null check (difficulty in ('easy','medium','hard')),
  focus_level text not null check (focus_level in ('short','medium','long')),
  time_preference text not null check (time_preference in ('day','midday','night')),
  created_at timestamptz default now()
);

-- suggested_slots: AI-suggested time blocks per task
create table if not exists public.suggested_slots (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  start_time timestamptz not null,
  end_time timestamptz not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  created_at timestamptz default now()
);

-- RLS
alter table public.calendar_tokens enable row level security;
alter table public.tasks enable row level security;
alter table public.suggested_slots enable row level security;

-- Service role can do anything; for API we use service key. For frontend we only need read/write via API.
-- Allow authenticated users to manage their own rows (if using anon key with RLS)
create policy "Users can manage own calendar_tokens"
  on public.calendar_tokens for all using (auth.uid() = user_id);

create policy "Users can manage own tasks"
  on public.tasks for all using (auth.uid() = user_id);

create policy "Users can manage own suggested_slots"
  on public.suggested_slots for all using (auth.uid() = user_id);

-- Indexes
create index if not exists tasks_user_id on public.tasks(user_id);
create index if not exists suggested_slots_task_id on public.suggested_slots(task_id);
create index if not exists suggested_slots_user_id on public.suggested_slots(user_id);
create index if not exists suggested_slots_start_time on public.suggested_slots(start_time);
