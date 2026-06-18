from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, String, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from verdictmesh.database import Base, utc_now
from verdictmesh.forecast_models import CouncilForecast, ForecastRequest


class ForecastRunRecord(Base):
    __tablename__ = "forecast_runs"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    question: Mapped[str] = mapped_column(String(3000))
    market_price_yes: Mapped[float] = mapped_column(Float)
    probability_yes: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float] = mapped_column(Float)
    upper_bound: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    disagreement: Mapped[float] = mapped_column(Float)
    evidence_coverage: Mapped[float] = mapped_column(Float)
    resolution_clarity: Mapped[float] = mapped_column(Float)
    average_evidence_quality: Mapped[float] = mapped_column(Float)
    raw_edge: Mapped[float] = mapped_column(Float)
    preferred_side: Mapped[str] = mapped_column(String(8))
    trade_allowed: Mapped[bool] = mapped_column(Boolean)
    no_trade_reasons: Mapped[list[str]] = mapped_column(JSON)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    forecast_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class ForecastRepository:
    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(
            database_url,
            echo=echo,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._sessions: sessionmaker[Session] = sessionmaker(
            self.engine, expire_on_commit=False
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def record(
        self,
        request: ForecastRequest,
        forecast: CouncilForecast,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                ForecastRunRecord(
                    run_id=forecast.run_id,
                    market_id=forecast.market_id,
                    question=request.question,
                    market_price_yes=forecast.market_price_yes,
                    probability_yes=forecast.probability_yes,
                    lower_bound=forecast.lower_bound,
                    upper_bound=forecast.upper_bound,
                    confidence=forecast.confidence,
                    disagreement=forecast.disagreement,
                    evidence_coverage=forecast.evidence_coverage,
                    resolution_clarity=forecast.resolution_clarity,
                    average_evidence_quality=forecast.average_evidence_quality,
                    raw_edge=forecast.raw_edge,
                    preferred_side=forecast.preferred_side.value,
                    trade_allowed=forecast.trade_allowed,
                    no_trade_reasons=list(forecast.no_trade_reasons),
                    request_payload=request.model_dump(mode="json"),
                    forecast_payload=forecast.model_dump(mode="json"),
                    created_at=forecast.created_at,
                )
            )

    def recent(self, limit: int = 100) -> list[CouncilForecast]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ForecastRunRecord)
                .order_by(ForecastRunRecord.created_at.desc())
                .limit(limit)
            ).all()
            return [
                CouncilForecast.model_validate(row.forecast_payload) for row in rows
            ]

    def count(self) -> int:
        with self._sessions() as session:
            value = session.scalar(select(func.count()).select_from(ForecastRunRecord))
            return int(value or 0)
