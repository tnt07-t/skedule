from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import auth, tasks, calendar as calendar_api, suggestions

app = FastAPI(title="Skedule API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(calendar_api.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(suggestions.router, prefix="/api/suggestions", tags=["suggestions"])


@app.get("/")
def root():
    return {"name": "Skedule API", "status": "ok"}
