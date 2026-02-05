from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Look for env in repo root first, then CWD.
    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).resolve().parent.parent / ".env",
            ".env",
        ]
    )

    supabase_url: str = ""
    # New Supabase key names with legacy aliases for compatibility.
    supabase_publishable_key: str = Field(
        default="",
        validation_alias=AliasChoices("supabase_publishable_key", "supabase_anon_key"),
    )
    supabase_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("supabase_secret_key", "supabase_service_key"),
    )
    # Only needed if you still mint/verify legacy JWTs yourself.
    supabase_jwt_secret: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"
    app_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # Backwards compatibility properties
    @property
    def supabase_anon_key(self) -> str:
        return self.supabase_publishable_key

    @property
    def supabase_service_key(self) -> str:
        return self.supabase_secret_key


settings = Settings()
