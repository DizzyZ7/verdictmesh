from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Side(StrEnum):
    YES = "YES"
    NO = "NO"


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class ResolutionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MarketSnapshot(BaseModel):
    market_id: str
    question: str
    slug: str | None = None
    condition_id: str | None = None
    token_id_yes: str | None = None
    token_id_no: str | None = None
    price_yes: float | None = Field(default=None, ge=0, le=1)
    price_no: float | None = Field(default=None, ge=0, le=1)
    liquidity_usd: float = Field(default=0, ge=0)
    volume_24h_usd: float = Field(default=0, ge=0)
    active: bool = True
    closed: bool = False


class TradeProposal(BaseModel):
    market_id: str = Field(min_length=1)
    side: Side
    fair_probability_yes: float = Field(ge=0, le=1)
    entry_price: float = Field(gt=0, lt=1)
    requested_stake: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    spread: float = Field(default=0, ge=0, le=1)
    estimated_slippage: float = Field(default=0, ge=0, le=1)
    liquidity_usd: float = Field(default=0, ge=0)
    resolution_risk: ResolutionRisk = ResolutionRisk.MEDIUM
    rationale: str = ""

    @property
    def fair_probability_for_side(self) -> float:
        if self.side is Side.YES:
            return self.fair_probability_yes
        return 1 - self.fair_probability_yes

    @property
    def raw_edge(self) -> float:
        return self.fair_probability_for_side - self.entry_price

    @property
    def net_edge(self) -> float:
        return self.raw_edge - self.spread - self.estimated_slippage


class RiskContext(BaseModel):
    bankroll: float = Field(gt=0)
    current_exposure: float = Field(default=0, ge=0)
    daily_pnl: float = 0
    mode: TradingMode = TradingMode.PAPER


class RiskDecision(BaseModel):
    approved: bool
    reasons: list[str]
    raw_edge: float
    net_edge: float
    approved_stake: float = Field(default=0, ge=0)


class PaperOrder(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    market_id: str
    side: Side
    price: float = Field(gt=0, lt=1)
    stake: float = Field(gt=0)
    quantity: float = Field(gt=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaperPosition(BaseModel):
    market_id: str
    side: Side
    quantity: float = Field(ge=0)
    average_price: float = Field(gt=0, lt=1)
    cost_basis: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_cost_basis(self) -> "PaperPosition":
        expected = self.quantity * self.average_price
        if abs(expected - self.cost_basis) > 1e-6:
            raise ValueError("cost_basis must equal quantity * average_price")
        return self


class DecisionAudit(BaseModel):
    decision_id: str
    market_id: str
    side: Side
    approved: bool
    reasons: list[str]
    raw_edge: float
    net_edge: float
    approved_stake: float
    created_at: datetime
