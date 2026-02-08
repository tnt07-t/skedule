# Skedule

Skedule suggests focused work blocks (study, etc.) in your free time using your Google Calendar and preferences. Barebones stack: **FastAPI** + **Supabase**.

## Features

- **Google OAuth** (Supabase Auth) + optional **Google Calendar** connect for free-busy and adding events
- **Profile**: display name, timezone, and free-text preferences (AI interprets)
- **Tasks**: name, short description, difficulty (easy/medium/hard), focus (short/medium/long blocks), time preference (day/midday/night)
- **AI plan**: uses task input + preferences + free time blocks to propose a time-block plan
- **Suggest slots**: fills free times in your calendar with suggested blocks; you **approve** (add to Google Calendar) or **reject**
- **UI**: week calendar with **dots** for suggested times; list of suggestions with Add/Reject
