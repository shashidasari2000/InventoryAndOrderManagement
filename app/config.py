from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Accounting Assistant"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    # On Vercel/serverless, skip create_all / schema bootstrap (big cold-start cost).
    # Run alembic offline instead. Set RUN_DB_BOOTSTRAP=true only for local first-run.
    RUN_DB_BOOTSTRAP: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/ai_accounting"

    # JWT
    SECRET_KEY: str = "change-this-to-a-strong-random-secret-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Encryption key for messages (32-byte Fernet key, base64 encoded)
    ENCRYPTION_KEY: str = "change-this-to-a-fernet-key-32bytes-base64"

    # OTP
    OTP_EXPIRE_MINUTES: int = 10
    OTP_LENGTH: int = 6
    # When true, SMS/WhatsApp is skipped and DEFAULT_OTP always works for login.
    USE_DEFAULT_OTP: bool = True
    DEFAULT_OTP: str = "123456"

    # SMS / OTP Provider (Twilio)
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    WHISPER_MODEL: str = "whisper-1"

    # Groq (free Whisper transcription)
    GROQ_API_KEY: Optional[str] = None

    # Sarvam AI (Indian language speech-to-text)
    SARVAM_API_KEY: Optional[str] = None

    # Google Gemini (fallback)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # WhatsApp Cloud API
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = "whatsapp_verify_token"
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v19.0"
    WHATSAPP_BUSINESS_NUMBER: Optional[str] = None
    WHATSAPP_OTP_TEMPLATE_NAME: Optional[str] = None
    WHATSAPP_OTP_TEMPLATE_LANGUAGE: str = "en_US"

    # Redis (Celery broker)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Azure Blob (voice file storage)
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    AZURE_BLOB_CONTAINER: str = "voice-messages"

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://yourdomain.com",
        "http://192.168.0.192:3000",
    ]
    ALLOW_ALL_ORIGINS: bool = False

    class Config:
        # Local: load .env if present. On Vercel: env vars from project settings.
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
