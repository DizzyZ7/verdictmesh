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

    database_url: str = "sqlite+pysqlite:///./verdictmesh.db"
    database_echo: bool = False
    database_auto_create: bool = True

    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_api_url: str = "https://clob.polymarket.com"
    market_scan_limit: int = Field(default=100, ge=1, le=500)
    order_book_scanner_enabled: bool = False
    order_book_scan_interval_seconds: int = Field(default=60, ge=10, le=86_400)
    order_book_scan_concurrency: int = Field(default=10, ge=1, le=50)
    order_book_market_limit: int = Field(default=50, ge=1, le=500)
    order_book_asset_limit: int = Field(default=100, ge=1, le=1_000)

    anthropic_api_key: str | None = None
    anthropic_api_url: str = "https://api.anthropic.com"
    forecast_model: str = "claude-sonnet-4-6"
    forecast_max_tokens: int = Field(default=2500, ge=256, le=64_000)
    forecast_min_agents: int = Field(default=3, ge=2, le=4)
    forecast_min_evidence: int = Field(default=2, ge=1, le=100)
    forecast_min_coverage: float = Field(default=0.50, ge=0, le=1)
    forecast_min_evidence_quality: float = Field(default=0.55, ge=0, le=1)
    forecast_min_confidence: float = Field(default=0.65, ge=0, le=1)
    forecast_max_disagreement: float = Field(default=0.15, ge=0, le=1)
    forecast_min_resolution_clarity: float = Field(default=0.75, ge=0, le=1)
    forecast_min_actionable_edge: float = Field(default=0.07, ge=0, le=1)

    paper_starting_cash: float = Field(default=10_000.0, gt=0)
    min_net_edge: float = Field(default=0.07, ge=0, le=1)
    min_confidence: float = Field(default=0.70, ge=0, le=1)
    min_liquidity_usd: float = Field(default=10_000.0, ge=0)
    max_spread: float = Field(default=0.025, ge=0, le=1)
    max_position_fraction: float = Field(default=0.01, gt=0, le=1)
    max_total_exposure_fraction: float = Field(default=0.10, gt=0, le=1)
    max_daily_loss_fraction: float = Field(default=0.02, gt=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
