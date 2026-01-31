# Skedule

Skedule suggests focused work blocks (study, etc.) in your free time using your Google Calendar and preferences. Barebones stack: **FastAPI** + **Supabase**.

## Features

- **Google OAuth** (Supabase Auth) + optional **Google Calendar** connect for free-busy and adding events
- **Tasks**: name, short description, difficulty (easy/medium/hard), focus (short/medium/long blocks), time preference (day/midday/night)
- **Suggest slots**: fills free times in your calendar with suggested blocks; you **approve** (add to Google Calendar) or **reject**
- **UI**: week calendar with **dots** for suggested times; list of suggestions with Add/Reject

## Setup

### 1. Supabase

- Create a project at [supabase.com](https://supabase.com).
- In **Authentication → Providers**, enable **Google** and add your OAuth client ID/secret.
- In **SQL Editor**, run the migration: `supabase/migrations/001_initial.sql`.
- In **Settings → API**: copy **Project URL**, **anon** key (for frontend), **service_role** key and **JWT Secret** (for backend).

### 2. Google Cloud (Calendar)

- Create a project in [Google Cloud Console](https://console.cloud.google.com).
- **APIs & Services → Credentials**: create **OAuth 2.0 Client ID** (Web application).
- Add authorized redirect URI: `http://localhost:8000/api/auth/google/callback` (or your backend URL).
- Copy Client ID and Client Secret.

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_JWT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, APP_URL, BACKEND_URL
uvicorn main:app --reload --port 8000
```

### 4. Frontend

- In `frontend/index.html`, set `SUPABASE_URL` and `SUPABASE_ANON_KEY` (from Supabase dashboard).
- Serve the frontend (must be same origin or configure CORS):

```bash
npx serve frontend -p 3000
```

Open `http://localhost:3000`. Sign in with Google, connect Google Calendar, add a task, click **Suggest slots**, then approve or reject suggestions. Dots on the week view show suggested times.

## Project layout

- `backend/` – FastAPI app: auth (Google Calendar OAuth), tasks, suggestions, calendar free-busy and add event
- `frontend/` – Single HTML page (Tailwind + Supabase JS)
- `supabase/migrations/` – Tables: `calendar_tokens`, `tasks`, `suggested_slots`
