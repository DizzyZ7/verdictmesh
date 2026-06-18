from pathlib import Path

import pytest

from verdictmesh.config import Settings
from verdictmesh.database import AuditRepository
from verdictmesh.domain import MarketSnapshot, ResolutionRisk, Side, TradeProposal
from verdictmesh.service import VerdictMeshService


def database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def approved_proposal() -> TradeProposal:
    return TradeProposal(
        market_id="market-1",
        side=Side.YES,
        fair_probability_yes=0.70,
        entry_price=0.50,
        requested_stake=500,
        confidence=0.90,
        spread=0.01,
        estimated_slippage=0.01,
        liquidity_usd=100_000,
        resolution_risk=ResolutionRisk.LOW,
        rationale="Test evidence",
    )


def test_market_snapshot_ingestion_is_idempotent(tmp_path: Path) -> None:
    repository = AuditRepository(database_url(tmp_path / "audit.db"))
    repository.create_schema()
    snapshot = MarketSnapshot(
        market_id="market-1",
        question="Will it happen?",
        price_yes=0.60,
        price_no=0.40,
        liquidity_usd=20_000,
        volume_24h_usd=5_000,
    )

    assert repository.record_markets([snapshot]) == 1
    assert repository.record_markets([snapshot]) == 0
    assert repository.counts()["market_snapshots"] == 1
    repository.close()


@pytest.mark.asyncio
async def test_paper_state_survives_service_restart(tmp_path: Path) -> None:
    settings = Settings(
        database_url=database_url(tmp_path / "service.db"),
        database_auto_create=True,
        paper_starting_cash=1_000,
    )
    first = VerdictMeshService(settings)

    decision, order = first.submit_paper_order(approved_proposal())

    assert decision.approved is True
    assert order is not None
    assert first.paper.cash == pytest.approx(990)
    await first.close()

    second = VerdictMeshService(settings)
    snapshot = second.paper.snapshot()

    assert snapshot["cash"] == pytest.approx(990)
    assert snapshot["exposure"] == pytest.approx(10)
    assert len(snapshot["orders"]) == 1
    assert len(snapshot["positions"]) == 1
    assert second.audit_counts()["trade_decisions"] == 1
    await second.close()


@pytest.mark.asyncio
async def test_rejected_proposal_is_audited(tmp_path: Path) -> None:
    settings = Settings(
        database_url=database_url(tmp_path / "rejected.db"),
        database_auto_create=True,
        paper_starting_cash=1_000,
    )
    service = VerdictMeshService(settings)
    proposal = approved_proposal().model_copy(
        update={"fair_probability_yes": 0.52, "entry_price": 0.50}
    )

    decision, order = service.submit_paper_order(proposal)

    assert decision.approved is False
    assert order is None
    audit = service.recent_decisions()
    assert len(audit) == 1
    assert audit[0].approved is False
    assert service.audit_counts()["paper_orders"] == 0
    await service.close()
