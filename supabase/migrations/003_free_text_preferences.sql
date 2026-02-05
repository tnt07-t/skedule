-- Add a free-text field for user preferences (keeps legacy JSON column for compatibility)
alter table public.user_profiles
  add column if not exists preferences_text text default ''::text;

-- Backfill: if text is empty but JSON has data, copy it as text
update public.user_profiles
set preferences_text = case
  when coalesce(preferences_text, '') = '' then
    case
      when preferences is null or preferences::text = '{}' then ''
      else preferences::text
    end
  else preferences_text
end;
