from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "VerdictMesh"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    trading_mode: str = "paper"
    live_trading_enabled: bool = False

    gamma_api_url: str = "https://gamma-api.polymarket.com"
    market_scan_limit: int = Field(default=100, ge=1, le=500)

    paper_starting_cash: float = Field(default=10_000.0, gt=0)
    min_net_edge: float = Field(default=0.07, ge=0, le=1)
    min_confidence: float = Field(default=0.70, ge=0, le=1)
    min_liquidity_usd: float = Field(default=10_000.0, ge=0)
    max_spread: float = Field(default=0.025, ge=0, le=1)
    max_position_fraction: float = Field(default=0.01, gt=0, le=1)
    max_total_exposure_fraction: float = Field(default=0.10, gt=0, le=1)
    max_daily_loss_fraction: float = Field(default=0.02, gt=0, le=1)

    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
