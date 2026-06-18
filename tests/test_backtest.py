import pytest

from verdictmesh.backtest import estimate_fill
from verdictmesh.domain import (
    OrderAction,
    OrderBookLevel,
    OrderBookSnapshot,
)


def order_book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        condition_id="condition-1",
        asset_id="asset-1",
        book_hash="hash-1",
        bids=[
            OrderBookLevel(price=0.48, size=10),
            OrderBookLevel(price=0.47, size=20),
        ],
        asks=[
            OrderBookLevel(price=0.52, size=5),
            OrderBookLevel(price=0.54, size=10),
        ],
    )


def test_buy_fill_walks_ask_depth() -> None:
    estimate = estimate_fill(order_book(), OrderAction.BUY, 5.30)

    assert estimate.fully_filled is True
    assert estimate.quantity == pytest.approx(10)
    assert estimate.average_price == pytest.approx(0.53)
    assert estimate.reference_price == pytest.approx(0.52)
    assert estimate.slippage == pytest.approx(0.01)
    assert estimate.worst_price == pytest.approx(0.54)


def test_buy_fill_reports_unfilled_notional() -> None:
    estimate = estimate_fill(order_book(), OrderAction.BUY, 100)

    assert estimate.fully_filled is False
    assert estimate.filled_amount == pytest.approx(8.0)
    assert estimate.unfilled_amount == pytest.approx(92.0)


def test_sell_fill_walks_bid_depth() -> None:
    estimate = estimate_fill(order_book(), OrderAction.SELL, 15)

    assert estimate.fully_filled is True
    assert estimate.quantity == pytest.approx(15)
    assert estimate.notional == pytest.approx(7.15)
    assert estimate.average_price == pytest.approx(7.15 / 15)
    assert estimate.slippage == pytest.approx(0.48 - 7.15 / 15)
