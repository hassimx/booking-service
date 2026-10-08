from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./booking.db"
    secret_key: str = ""
    admin_username: str = ""
    admin_password_hash: str = ""
    cookie_secure: bool = False
    timezone: str = "Asia/Almaty"
    shop_name: str = "Nord"
    currency: str = "₸"
    days_ahead: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
