alter table public.tasks
  add column if not exists estimate_updated_at timestamptz;
