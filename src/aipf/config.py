from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aipf.models import ApiStyle


class Settings(BaseSettings):
    base_url: str
    api_key: SecretStr
    timeout_s: int = 90
    model: str | None = None
    api_style: ApiStyle | Literal["auto"] = "auto"
    latency_rounds: int = 5

    @field_validator("base_url")
    @classmethod
    def _base_url_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("base URL cannot be empty")
        return value

    @field_validator("api_key")
    @classmethod
    def _api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API key cannot be empty")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AIPF_",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    @property
    def base_url_normalized(self) -> str:
        return self.base_url.rstrip("/")
