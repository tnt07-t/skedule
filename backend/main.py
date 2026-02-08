from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import auth, tasks, calendar as calendar_api, suggestions, profile, llm
from config import settings

app = FastAPI(title="Skedule API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https://[a-z0-9-]+\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(calendar_api.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(suggestions.router, prefix="/api/suggestions", tags=["suggestions"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(llm.router, prefix="/api/plan", tags=["plan"])


@app.get("/api/config")
def public_config():
    return {
        "supabase_url": settings.supabase_url,
        "supabase_publishable_key": settings.supabase_publishable_key,
        # legacy field for older frontends
        "supabase_anon_key": settings.supabase_anon_key,
    }


@app.get("/")
def root():
    return {"name": "Skedule API", "status": "ok"}
