from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Coach"
    database_url: str = "sqlite:///./ai_coach.db"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:latest"
    ollama_embed_model: str = "embeddinggemma"
    chatgpt_public_base_url: str = ""
    chatgpt_action_token: str = ""
    chatgpt_sync_target_url: str = ""
    chatgpt_sync_target_token: str = ""
    app_secret: str = "dev-only-change-me"
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_redirect_uri: str = "http://localhost:8000/api/connectors/strava/callback"
    strava_verify_token: str = "local-dev-token"
    garmin_non_official_enabled: bool = False
    garmin_import_dir: str = "./garmin_files"
    coach_context_export_path: str = "./coach_context.md"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
