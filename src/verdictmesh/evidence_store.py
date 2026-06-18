from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from verdictmesh.database import Base, utc_now
from verdictmesh.evidence_models import EvidenceCollectionRequest, EvidencePackage


class EvidencePackageRecord(Base):
    __tablename__ = "evidence_packages"

    package_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    market_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(String(2000))
    candidates_found: Mapped[int] = mapped_column(Integer)
    evidence_count: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    package_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class EvidenceRepository:
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
        request: EvidenceCollectionRequest,
        package: EvidencePackage,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                EvidencePackageRecord(
                    package_id=package.package_id,
                    market_id=package.market_id,
                    provider=package.provider,
                    query=package.query,
                    candidates_found=package.candidates_found,
                    evidence_count=len(package.evidence),
                    warnings=list(package.warnings),
                    request_payload=request.model_dump(mode="json"),
                    package_payload=package.model_dump(mode="json"),
                    created_at=package.created_at,
                )
            )

    def recent(self, limit: int = 100) -> list[EvidencePackage]:
        with self._sessions() as session:
            rows = session.scalars(
                select(EvidencePackageRecord)
                .order_by(EvidencePackageRecord.created_at.desc())
                .limit(limit)
            ).all()
            return [EvidencePackage.model_validate(row.package_payload) for row in rows]

    def count(self) -> int:
        with self._sessions() as session:
            value = session.scalar(select(func.count()).select_from(EvidencePackageRecord))
            return int(value or 0)
