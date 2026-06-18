import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from verdictmesh.domain import (
    DecisionAudit,
    MarketSnapshot,
    PaperOrder,
    PaperPosition,
    RiskContext,
    RiskDecision,
    Side,
    TradeProposal,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class MarketRecord(Base):
    __tablename__ = "markets"

    market_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    question: Mapped[str] = mapped_column(String(2000))
    slug: Mapped[str | None] = mapped_column(String(512))
    condition_id: Mapped[str | None] = mapped_column(String(256))
    token_id_yes: Mapped[str | None] = mapped_column(String(256))
    token_id_no: Mapped[str | None] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint("market_id", "snapshot_hash", name="uq_market_snapshot_state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(
        ForeignKey("markets.market_id", ondelete="CASCADE"), index=True
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    price_yes: Mapped[float | None] = mapped_column(Float)
    price_no: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float] = mapped_column(Float)
    volume_24h_usd: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean)
    closed: Mapped[bool] = mapped_column(Boolean)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TradeDecisionRecord(Base):
    __tablename__ = "trade_decisions"

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    side: Mapped[str] = mapped_column(String(8))
    fair_probability_yes: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    requested_stake: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    spread: Mapped[float] = mapped_column(Float)
    estimated_slippage: Mapped[float] = mapped_column(Float)
    liquidity_usd: Mapped[float] = mapped_column(Float)
    resolution_risk: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(String(5000), default="")
    context_bankroll: Mapped[float] = mapped_column(Float)
    context_exposure: Mapped[float] = mapped_column(Float)
    context_daily_pnl: Mapped[float] = mapped_column(Float)
    context_mode: Mapped[str] = mapped_column(String(16))
    approved: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list[str]] = mapped_column(JSON)
    raw_edge: Mapped[float] = mapped_column(Float)
    net_edge: Mapped[float] = mapped_column(Float)
    approved_stake: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PaperOrderRecord(Base):
    __tablename__ = "paper_orders"

    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("trade_decisions.decision_id", ondelete="RESTRICT"), unique=True
    )
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    side: Mapped[str] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperPositionRecord(Base):
    __tablename__ = "paper_positions"

    market_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    side: Mapped[str] = mapped_column(String(8), primary_key=True)
    quantity: Mapped[float] = mapped_column(Float)
    average_price: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PortfolioStateRecord(Base):
    __tablename__ = "portfolio_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    starting_cash: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


@dataclass(frozen=True, slots=True)
class PaperState:
    starting_cash: float
    cash: float
    orders: list[PaperOrder]
    positions: list[PaperPosition]


class AuditRepository:
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

    def initialize_portfolio(self, starting_cash: float) -> PaperState:
        with self._sessions.begin() as session:
            state = session.get(PortfolioStateRecord, 1)
            if state is None:
                session.add(
                    PortfolioStateRecord(id=1, starting_cash=starting_cash, cash=starting_cash)
                )
        return self.load_paper_state()

    def load_paper_state(self) -> PaperState:
        with self._sessions() as session:
            state = session.get(PortfolioStateRecord, 1)
            if state is None:
                raise RuntimeError("paper portfolio has not been initialized")
            order_rows = session.scalars(
                select(PaperOrderRecord).order_by(PaperOrderRecord.created_at)
            ).all()
            position_rows = session.scalars(
                select(PaperPositionRecord).order_by(
                    PaperPositionRecord.market_id, PaperPositionRecord.side
                )
            ).all()
            return PaperState(
                starting_cash=state.starting_cash,
                cash=state.cash,
                orders=[self._to_order(row) for row in order_rows],
                positions=[self._to_position(row) for row in position_rows],
            )

    def record_markets(self, snapshots: Sequence[MarketSnapshot]) -> int:
        inserted = 0
        with self._sessions.begin() as session:
            for snapshot in snapshots:
                market = session.get(MarketRecord, snapshot.market_id)
                if market is None:
                    market = MarketRecord(market_id=snapshot.market_id, question=snapshot.question)
                    session.add(market)
                self._update_market(market, snapshot)

                snapshot_hash = self._snapshot_hash(snapshot)
                exists = session.scalar(
                    select(MarketSnapshotRecord.id).where(
                        MarketSnapshotRecord.market_id == snapshot.market_id,
                        MarketSnapshotRecord.snapshot_hash == snapshot_hash,
                    )
                )
                if exists is not None:
                    continue
                session.add(
                    MarketSnapshotRecord(
                        market_id=snapshot.market_id,
                        snapshot_hash=snapshot_hash,
                        price_yes=snapshot.price_yes,
                        price_no=snapshot.price_no,
                        liquidity_usd=snapshot.liquidity_usd,
                        volume_24h_usd=snapshot.volume_24h_usd,
                        active=snapshot.active,
                        closed=snapshot.closed,
                    )
                )
                inserted += 1
        return inserted

    def record_decision(
        self,
        proposal: TradeProposal,
        context: RiskContext,
        decision: RiskDecision,
    ) -> str:
        decision_id = str(uuid4())
        with self._sessions.begin() as session:
            session.add(self._decision_record(decision_id, proposal, context, decision))
        return decision_id

    def commit_paper_order(
        self,
        *,
        proposal: TradeProposal,
        context: RiskContext,
        decision: RiskDecision,
        order: PaperOrder,
        resulting_cash: float,
        resulting_position: PaperPosition,
    ) -> str:
        decision_id = str(uuid4())
        with self._sessions.begin() as session:
            session.add(self._decision_record(decision_id, proposal, context, decision))
            session.add(
                PaperOrderRecord(
                    order_id=order.order_id,
                    decision_id=decision_id,
                    market_id=order.market_id,
                    side=order.side.value,
                    price=order.price,
                    stake=order.stake,
                    quantity=order.quantity,
                    created_at=order.created_at,
                )
            )

            state = session.get(PortfolioStateRecord, 1)
            if state is None:
                raise RuntimeError("paper portfolio has not been initialized")
            state.cash = resulting_cash

            position = session.get(
                PaperPositionRecord,
                (resulting_position.market_id, resulting_position.side.value),
            )
            if position is None:
                position = PaperPositionRecord(
                    market_id=resulting_position.market_id,
                    side=resulting_position.side.value,
                    quantity=resulting_position.quantity,
                    average_price=resulting_position.average_price,
                    cost_basis=resulting_position.cost_basis,
                )
                session.add(position)
            else:
                position.quantity = resulting_position.quantity
                position.average_price = resulting_position.average_price
                position.cost_basis = resulting_position.cost_basis
        return decision_id

    def recent_decisions(self, limit: int = 100) -> list[DecisionAudit]:
        with self._sessions() as session:
            rows = session.scalars(
                select(TradeDecisionRecord)
                .order_by(TradeDecisionRecord.created_at.desc())
                .limit(limit)
            ).all()
            return [
                DecisionAudit(
                    decision_id=row.decision_id,
                    market_id=row.market_id,
                    side=Side(row.side),
                    approved=row.approved,
                    reasons=list(row.reasons),
                    raw_edge=row.raw_edge,
                    net_edge=row.net_edge,
                    approved_stake=row.approved_stake,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def counts(self) -> dict[str, int]:
        with self._sessions() as session:
            return {
                "markets": self._count(session, MarketRecord),
                "market_snapshots": self._count(session, MarketSnapshotRecord),
                "trade_decisions": self._count(session, TradeDecisionRecord),
                "paper_orders": self._count(session, PaperOrderRecord),
                "paper_positions": self._count(session, PaperPositionRecord),
            }

    @staticmethod
    def _count(session: Session, model: type[Base]) -> int:
        value = session.scalar(select(func.count()).select_from(model))
        return int(value or 0)

    @staticmethod
    def _update_market(market: MarketRecord, snapshot: MarketSnapshot) -> None:
        market.question = snapshot.question
        market.slug = snapshot.slug
        market.condition_id = snapshot.condition_id
        market.token_id_yes = snapshot.token_id_yes
        market.token_id_no = snapshot.token_id_no
        market.active = snapshot.active
        market.closed = snapshot.closed
        market.updated_at = utc_now()

    @staticmethod
    def _snapshot_hash(snapshot: MarketSnapshot) -> str:
        payload = json.dumps(
            {
                "price_yes": snapshot.price_yes,
                "price_no": snapshot.price_no,
                "liquidity_usd": snapshot.liquidity_usd,
                "volume_24h_usd": snapshot.volume_24h_usd,
                "active": snapshot.active,
                "closed": snapshot.closed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _decision_record(
        decision_id: str,
        proposal: TradeProposal,
        context: RiskContext,
        decision: RiskDecision,
    ) -> TradeDecisionRecord:
        return TradeDecisionRecord(
            decision_id=decision_id,
            market_id=proposal.market_id,
            side=proposal.side.value,
            fair_probability_yes=proposal.fair_probability_yes,
            entry_price=proposal.entry_price,
            requested_stake=proposal.requested_stake,
            confidence=proposal.confidence,
            spread=proposal.spread,
            estimated_slippage=proposal.estimated_slippage,
            liquidity_usd=proposal.liquidity_usd,
            resolution_risk=proposal.resolution_risk.value,
            rationale=proposal.rationale,
            context_bankroll=context.bankroll,
            context_exposure=context.current_exposure,
            context_daily_pnl=context.daily_pnl,
            context_mode=context.mode.value,
            approved=decision.approved,
            reasons=list(decision.reasons),
            raw_edge=decision.raw_edge,
            net_edge=decision.net_edge,
            approved_stake=decision.approved_stake,
        )

    @staticmethod
    def _to_order(row: PaperOrderRecord) -> PaperOrder:
        return PaperOrder(
            order_id=row.order_id,
            market_id=row.market_id,
            side=Side(row.side),
            price=row.price,
            stake=row.stake,
            quantity=row.quantity,
            created_at=row.created_at,
        )

    @staticmethod
    def _to_position(row: PaperPositionRecord) -> PaperPosition:
        return PaperPosition(
            market_id=row.market_id,
            side=Side(row.side),
            quantity=row.quantity,
            average_price=row.average_price,
            cost_basis=row.cost_basis,
        )
