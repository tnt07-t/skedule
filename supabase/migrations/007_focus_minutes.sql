-- Add focus_minutes column to tasks
alter table tasks add column if not exists focus_minutes integer;
