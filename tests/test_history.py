from pathlib import Path

import pytest

from verdictmesh.domain import (
    OrderBookLevel,
    OrderBookSnapshot,
    Outcome,
)
from verdictmesh.history import HistoryRepository


def database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_orderbook_storage_is_idempotent(tmp_path: Path) -> None:
    repository = HistoryRepository(database_url(tmp_path / "history.db"))
    repository.create_schema()
    snapshot = OrderBookSnapshot(
        app_market_id="market-1",
        condition_id="condition-1",
        asset_id="asset-1",
        outcome=Outcome.YES,
        book_hash="hash-1",
        bids=[OrderBookLevel(price=0.48, size=10)],
        asks=[OrderBookLevel(price=0.52, size=5)],
        tick_size=0.01,
        min_order_size=5,
    )

    assert repository.record_order_books([snapshot]) == 1
    assert repository.record_order_books([snapshot]) == 0
    assert repository.count() == 1

    restored = repository.latest_order_book("asset-1")
    assert restored is not None
    assert restored.outcome is Outcome.YES
    assert restored.best_bid == pytest.approx(0.48)
    assert restored.best_ask == pytest.approx(0.52)
    assert restored.spread == pytest.approx(0.04)
    repository.close()
