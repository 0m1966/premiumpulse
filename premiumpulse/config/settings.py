"""Settings and runtime configuration for PremiumPulse."""

import os
from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for PremiumPulse, loading from environment or st.secrets."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Operational Mode
    PREMIUMPULSE_MODE: Literal["LIVE", "SNAPSHOT"] = Field(default="SNAPSHOT")
    PREMIUMPULSE_PORT: int = Field(default=8000)
    PREMIUMPULSE_HOST: str = Field(default="0.0.0.0")
    PREMIUMPULSE_API_KEY: str = Field(default="pp-dev-secret-key-98765")

    # Snowflake Settings
    SNOWFLAKE_ACCOUNT: str | None = Field(default=None)
    SNOWFLAKE_USER: str | None = Field(default=None)
    SNOWFLAKE_PASSWORD: str | None = Field(default=None)
    SNOWFLAKE_WAREHOUSE: str = Field(default="PP_WH")
    SNOWFLAKE_DATABASE: str = Field(default="PREMIUMPULSE_DB")
    SNOWFLAKE_SCHEMA: str = Field(default="MART")
    SNOWFLAKE_ROLE: str = Field(default="PP_VIEWER")

    # Databricks Settings
    DATABRICKS_HOST: str | None = Field(default=None)
    DATABRICKS_TOKEN: str | None = Field(default=None)
    DATABRICKS_CATALOG: str = Field(default="workspace")
    DATABRICKS_SCHEMA: str = Field(default="premiumpulse")
    DATABRICKS_VOLUME: str = Field(default="landing_zone")

    # Groq LLM Settings
    GROQ_API_KEY: str | None = Field(default=None)
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    PROMPT_VERSION: str = Field(default="1.0.0")

    @property
    def is_snowflake_configured(self) -> bool:
        """Return True if required Snowflake credentials are fully configured."""
        return bool(
            self.SNOWFLAKE_ACCOUNT
            and self.SNOWFLAKE_USER
            and self.SNOWFLAKE_PASSWORD
        )

    @property
    def is_databricks_configured(self) -> bool:
        """Return True if Databricks credentials are provided."""
        return bool(self.DATABRICKS_HOST and self.DATABRICKS_TOKEN)

    @property
    def is_groq_configured(self) -> bool:
        """Return True if Groq API key is present."""
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    # Attempt to load from streamlit secrets if available
    try:
        import streamlit as st

        if hasattr(st, "secrets") and len(st.secrets) > 0:
            overrides = {}
            for key in Settings.model_fields.keys():
                if key in st.secrets:
                    overrides[key] = st.secrets[key]
            if overrides:
                return Settings(**overrides)
    except Exception:
        pass
    return Settings()
