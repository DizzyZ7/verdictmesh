from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from verdictmesh.database import Base, utc_now
from verdictmesh.domain import OrderBookLevel, OrderBookSnapshot, Outcome


class OrderBookSnapshotRecord(Base):
    __tablename__ = "order_book_snapshots"
    __table_args__ = (
        UniqueConstraint("asset_id", "book_hash", name="uq_order_book_asset_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_market_id: Mapped[str | None] = mapped_column(String(128), index=True)
    condition_id: Mapped[str] = mapped_column(String(256), index=True)
    asset_id: Mapped[str] = mapped_column(String(256), index=True)
    outcome: Mapped[str | None] = mapped_column(String(8))
    source_timestamp: Mapped[str | None] = mapped_column(String(64))
    book_hash: Mapped[str] = mapped_column(String(128))
    best_bid: Mapped[float | None] = mapped_column(Float)
    best_ask: Mapped[float | None] = mapped_column(Float)
    midpoint: Mapped[float | None] = mapped_column(Float)
    spread: Mapped[float | None] = mapped_column(Float)
    bid_notional: Mapped[float] = mapped_column(Float)
    ask_notional: Mapped[float] = mapped_column(Float)
    min_order_size: Mapped[float | None] = mapped_column(Float)
    tick_size: Mapped[float | None] = mapped_column(Float)
    neg_risk: Mapped[bool] = mapped_column(Boolean)
    bids: Mapped[list[dict[str, float]]] = mapped_column(JSON)
    asks: Mapped[list[dict[str, float]]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class HistoryRepository:
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

    def record_order_books(self, snapshots: Sequence[OrderBookSnapshot]) -> int:
        inserted = 0
        with self._sessions.begin() as session:
            for snapshot in snapshots:
                exists = session.scalar(
                    select(OrderBookSnapshotRecord.id).where(
                        OrderBookSnapshotRecord.asset_id == snapshot.asset_id,
                        OrderBookSnapshotRecord.book_hash == snapshot.book_hash,
                    )
                )
                if exists is not None:
                    continue
                session.add(self._to_record(snapshot))
                inserted += 1
        return inserted

    def list_order_books(
        self,
        asset_id: str,
        limit: int = 100,
    ) -> list[OrderBookSnapshot]:
        with self._sessions() as session:
            rows = session.scalars(
                select(OrderBookSnapshotRecord)
                .where(OrderBookSnapshotRecord.asset_id == asset_id)
                .order_by(OrderBookSnapshotRecord.fetched_at.desc())
                .limit(limit)
            ).all()
            return [self._to_domain(row) for row in rows]

    def latest_order_book(self, asset_id: str) -> OrderBookSnapshot | None:
        rows = self.list_order_books(asset_id, 1)
        return rows[0] if rows else None

    def count(self) -> int:
        with self._sessions() as session:
            value = session.scalar(
                select(func.count()).select_from(OrderBookSnapshotRecord)
            )
            return int(value or 0)

    @staticmethod
    def _to_record(snapshot: OrderBookSnapshot) -> OrderBookSnapshotRecord:
        return OrderBookSnapshotRecord(
            app_market_id=snapshot.app_market_id,
            condition_id=snapshot.condition_id,
            asset_id=snapshot.asset_id,
            outcome=snapshot.outcome.value if snapshot.outcome else None,
            source_timestamp=snapshot.source_timestamp,
            book_hash=snapshot.book_hash,
            best_bid=snapshot.best_bid,
            best_ask=snapshot.best_ask,
            midpoint=snapshot.midpoint,
            spread=snapshot.spread,
            bid_notional=snapshot.bid_notional,
            ask_notional=snapshot.ask_notional,
            min_order_size=snapshot.min_order_size,
            tick_size=snapshot.tick_size,
            neg_risk=snapshot.neg_risk,
            bids=[level.model_dump() for level in snapshot.bids],
            asks=[level.model_dump() for level in snapshot.asks],
            fetched_at=snapshot.fetched_at,
        )

    @staticmethod
    def _to_domain(row: OrderBookSnapshotRecord) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            app_market_id=row.app_market_id,
            condition_id=row.condition_id,
            asset_id=row.asset_id,
            outcome=Outcome(row.outcome) if row.outcome else None,
            source_timestamp=row.source_timestamp,
            book_hash=row.book_hash,
            bids=[OrderBookLevel.model_validate(level) for level in row.bids],
            asks=[OrderBookLevel.model_validate(level) for level in row.asks],
            min_order_size=row.min_order_size,
            tick_size=row.tick_size,
            neg_risk=row.neg_risk,
            fetched_at=row.fetched_at,
        )
