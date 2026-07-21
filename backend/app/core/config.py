from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Mock HRMS API"
    environment: str = "dev"
    app_timezone: str = "Asia/Kolkata"
    database_url: str = "sqlite+aiosqlite:///./storage/hrms.db"

    jwt_secret_key: str = "change_me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    policy_upload_dir: str = "/app/storage/hr-policies"
    profile_photo_upload_dir: str = "/app/storage/profile-photos"
    employee_document_upload_dir: str = "/app/storage/employee-documents"

    # --- AI / Phase-4 settings ---
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    chroma_db_path: str = "./storage/chroma_db"
    # Base URL this backend is reachable at (used by action-agent for self-calls)
    internal_api_base_url: str = "http://localhost:8000"
    ai_sql_row_limit: int = 50


settings = Settings()
