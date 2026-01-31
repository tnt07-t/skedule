from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    app_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
