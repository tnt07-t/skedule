# Skedule

Skedule suggests focused work blocks (study, etc.) in your free time using your Google Calendar and preferences. Barebones stack: **FastAPI** + **Supabase**.

## Features

- **Google OAuth** (Supabase Auth) + optional **Google Calendar** connect for free-busy and adding events
- **Profile**: display name, timezone, and free-text preferences (AI interprets)
- **Tasks**: name, short description, difficulty (easy/medium/hard), focus (short/medium/long blocks), time preference (day/midday/night)
- **AI plan**: uses task input + preferences + free time blocks to propose a time-block plan
- **Suggest slots**: fills free times in your calendar with suggested blocks; you **approve** (add to Google Calendar) or **reject**
- **UI**: week calendar with **dots** for suggested times; list of suggestions with Add/Reject

## Setup

### 1. Supabase

- Create a project at [supabase.com](https://supabase.com).
- In **Authentication → Providers**, enable **Google** and add your OAuth client ID/secret.
- In **SQL Editor**, run the migrations: `supabase/migrations/001_initial.sql`, `supabase/migrations/002_user_profiles.sql`, and `supabase/migrations/003_free_text_preferences.sql`.
- In **Settings → API → API Keys**, copy **Project URL**, **Publishable** key (`sb_publishable_...` for frontend) and **Secret** key (`sb_secret_...` for backend). JWT Secret is legacy/optional.

### 2. Google Cloud (Calendar)

- Create a project in [Google Cloud Console](https://console.cloud.google.com).
- **APIs & Services → Credentials**: create **OAuth 2.0 Client ID** (Web application).
- Add authorized redirect URI: `http://localhost:8000/api/auth/google/callback` (or your backend URL).
- Copy Client ID and Client Secret.

### 3. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
# Edit .env: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY, SUPABASE_JWT_SECRET (optional), GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GEMINI_API_KEY, GEMINI_MODEL, APP_URL, BACKEND_URL
uvicorn main:app --reload --port 8000
```

### 4. Frontend

- In `frontend/index.html`, set `SUPABASE_URL` and `SUPABASE_ANON_KEY` (use the **Publishable** key; variable name kept for compatibility).
- Serve the frontend (must be same origin or configure CORS):

```bash
cd frontend
npx serve . -p 3000
```

Open `http://localhost:3000`. Sign in with Google, connect Google Calendar, add a task, click **Suggest slots**, then approve or reject suggestions. Dots on the week view show suggested times.

## Project layout

- `backend/` – FastAPI app: auth (Google Calendar OAuth), tasks, suggestions, calendar free-busy and add event
- `frontend/` – Single HTML page (Tailwind + Supabase JS)
- `supabase/migrations/` – Tables: `calendar_tokens`, `tasks`, `suggested_slots`
