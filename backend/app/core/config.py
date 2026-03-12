from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vanigan ID Card MVP"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"

    mongo_url: str = "mongodb://mongodb:27017"
    mongo_db_name: str = "vanigan"

    redis_url: str = "redis://redis:6379/0"

    frontend_url: str = "http://localhost:5173"
    backend_public_url: str = "http://localhost:8000"

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""

    admin_api_key: str = "change-this-admin-key"

    otp_ttl_seconds: int = 300
    verify_ttl_seconds: int = 900

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_verify_token: str = "vanigan_whatsapp_verify_2026"
    whatsapp_public_base_url: str = ""
    whatsapp_download_template_name: str = ""
    whatsapp_download_template_lang: str = "en"
    whatsapp_view_template_name: str = ""
    whatsapp_view_template_lang: str = "en"
    whatsapp_referral_template_name: str = ""
    whatsapp_referral_template_lang: str = "en"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
