import pytest

from verdictmesh.domain import ResolutionRisk, RiskContext, Side, TradeProposal, TradingMode
from verdictmesh.risk import RiskEngine, RiskLimits


def proposal(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "market_id": "market-1",
        "side": Side.YES,
        "fair_probability_yes": 0.65,
        "entry_price": 0.50,
        "requested_stake": 500.0,
        "confidence": 0.80,
        "spread": 0.01,
        "estimated_slippage": 0.01,
        "liquidity_usd": 50_000.0,
        "resolution_risk": ResolutionRisk.LOW,
    }
    values.update(overrides)
    return TradeProposal(**values)


def test_approved_trade_is_capped_by_position_limit() -> None:
    engine = RiskEngine(RiskLimits())
    context = RiskContext(bankroll=10_000, current_exposure=0, daily_pnl=0)

    decision = engine.evaluate(proposal(), context)

    assert decision.approved is True
    assert decision.approved_stake == pytest.approx(100)
    assert decision.net_edge == pytest.approx(0.13)


def test_low_edge_is_rejected() -> None:
    engine = RiskEngine(RiskLimits())
    context = RiskContext(bankroll=10_000)

    decision = engine.evaluate(
        proposal(fair_probability_yes=0.56, entry_price=0.50),
        context,
    )

    assert decision.approved is False
    assert "Net edge is below the minimum" in decision.reasons


def test_live_trade_is_rejected_by_default() -> None:
    engine = RiskEngine(RiskLimits(live_trading_enabled=False))
    context = RiskContext(bankroll=10_000, mode=TradingMode.LIVE)

    decision = engine.evaluate(proposal(), context)

    assert decision.approved is False
    assert "Live trading is disabled" in decision.reasons


def test_no_side_uses_inverse_probability() -> None:
    engine = RiskEngine(RiskLimits(min_net_edge=0.05))
    context = RiskContext(bankroll=10_000)

    decision = engine.evaluate(
        proposal(
            side=Side.NO,
            fair_probability_yes=0.30,
            entry_price=0.55,
            spread=0.01,
            estimated_slippage=0.01,
        ),
        context,
    )

    assert decision.approved is True
    assert decision.net_edge == pytest.approx(0.13)
