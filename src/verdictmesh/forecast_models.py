from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentRole(StrEnum):
    RESEARCHER = "researcher"
    DOMAIN_EXPERT = "domain_expert"
    SKEPTIC = "skeptic"
    RESOLUTION_AUDITOR = "resolution_auditor"


class PreferredSide(StrEnum):
    YES = "YES"
    NO = "NO"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(default="", max_length=500)
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    excerpt: str = Field(min_length=1, max_length=5000)
    authority_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_id: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=3000)
    resolution_rules: str = Field(min_length=1, max_length=10_000)
    resolution_source: str = Field(default="", max_length=2048)
    category: str = Field(default="general", max_length=100)
    market_price_yes: float = Field(gt=0, lt=1)
    close_time: datetime | None = None
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> "ForecastRequest":
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        return self


class AgentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probability_yes: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    counter_evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    resolution_clarity: float = Field(ge=0, le=1)
    information_already_priced_in: bool
    abstain: bool = False
    abstain_reason: str | None = None


class AgentForecast(AgentAnalysis):
    role: AgentRole
    model_id: str
    prompt_version: str = "council-v1"


class CouncilForecast(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    market_id: str
    market_price_yes: float = Field(gt=0, lt=1)
    probability_yes: float = Field(ge=0, le=1)
    lower_bound: float = Field(ge=0, le=1)
    upper_bound: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    disagreement: float = Field(ge=0)
    evidence_coverage: float = Field(ge=0, le=1)
    resolution_clarity: float = Field(ge=0, le=1)
    average_evidence_quality: float = Field(ge=0, le=1)
    raw_edge: float
    preferred_side: PreferredSide
    trade_allowed: bool
    no_trade_reasons: list[str]
    agents: list[AgentForecast]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConsensusRequest(BaseModel):
    request: ForecastRequest
    agents: list[AgentForecast] = Field(min_length=1, max_length=10)
