from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from verdictmesh.forecast_models import EvidenceItem


class EvidenceSourceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=1000)
    domain: str = Field(default="", max_length=255)
    publisher: str = Field(default="", max_length=500)
    published_at: datetime | None = None
    language: str = Field(default="", max_length=64)
    source_country: str = Field(default="", max_length=128)
    snippet: str = Field(default="", max_length=5000)
    image_url: str | None = Field(default=None, max_length=2048)


class EvidenceCollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=3, max_length=3000)
    resolution_rules: str = Field(min_length=1, max_length=10_000)
    market_price_yes: float = Field(gt=0, lt=1)
    resolution_source: str = Field(default="", max_length=2048)
    category: str = Field(default="general", max_length=100)
    close_time: datetime | None = None
    extra_queries: list[str] = Field(default_factory=list, max_length=10)
    trusted_domains: list[str] = Field(default_factory=list, max_length=50)


class EvidencePackage(BaseModel):
    package_id: str = Field(default_factory=lambda: str(uuid4()))
    market_id: str
    query: str
    provider: str
    candidates_found: int = Field(ge=0)
    evidence: list[EvidenceItem]
    rejected_urls: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceCollectionResult(BaseModel):
    package: EvidencePackage
    forecast_ready: bool
    forecast_blockers: list[str] = Field(default_factory=list)


class SourceDomain(BaseModel):
    domain: str
    authority_score: float = Field(ge=0, le=1)
    reason: str


class EvidenceHealth(BaseModel):
    provider: str
    configured: bool
    base_url: HttpUrl | str
