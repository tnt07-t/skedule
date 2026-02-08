alter table public.tasks
  add column if not exists estimated_minutes integer;
