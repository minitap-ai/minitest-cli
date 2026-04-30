"""Application configuration via pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_URL = "https://testing-service.app.minitap.ai"
DEFAULT_APPS_MANAGER_URL = "https://apps-manager.app.minitap.ai"
DEFAULT_INTEGRATIONS_URL = "https://integrations.minitap.ai"
DEFAULT_CONFIG_DIR = Path.home() / ".minitest"
DEFAULT_SUPABASE_URL = "https://auth.minitap.ai"
DEFAULT_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_mlpTSxXqh7L3p5EY8FBEDA_yWma_vrf"


class Settings(BaseSettings):
    """Global CLI configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MINITEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_url: str = Field(
        default=DEFAULT_API_URL,
        description="Base URL of the Minitest API",
    )
    apps_manager_url: str = Field(
        default=DEFAULT_APPS_MANAGER_URL,
        description="Base URL of the apps-manager service (MINITEST_APPS_MANAGER_URL)",
    )
    integrations_url: str = Field(
        default=DEFAULT_INTEGRATIONS_URL,
        description="Base URL of the minihands-integrations service (MINITEST_INTEGRATIONS_URL)",
    )
    config_dir: Path = Field(
        default=DEFAULT_CONFIG_DIR,
        description="Directory for CLI config and cache files (~/.minitest)",
    )
    token: str | None = Field(
        default=None,
        description="API authentication token (MINITEST_TOKEN)",
    )
    app_id: str | None = Field(
        default=None,
        description="Default app ID (MINITEST_APP_ID)",
    )
    supabase_url: str = Field(
        default=DEFAULT_SUPABASE_URL,
        description="Supabase project URL for OAuth (MINITEST_SUPABASE_URL)",
    )
    supabase_publishable_key: str = Field(
        default=DEFAULT_SUPABASE_PUBLISHABLE_KEY,
        description="Supabase publishable key (MINITEST_SUPABASE_PUBLISHABLE_KEY)",
    )

    def ensure_config_dir(self) -> Path:
        """Create the config directory if it doesn't exist and return the path."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        return self.config_dir


def get_settings() -> Settings:
    """Create and return a Settings instance."""
    return Settings()
