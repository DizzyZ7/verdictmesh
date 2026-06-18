import pytest

from verdictmesh.domain import ResolutionRisk, RiskDecision, Side, TradeProposal
from verdictmesh.paper import PaperBroker


def test_paper_order_updates_cash_position_and_equity() -> None:
    broker = PaperBroker(starting_cash=1_000)
    proposal = TradeProposal(
        market_id="market-1",
        side=Side.YES,
        fair_probability_yes=0.70,
        entry_price=0.50,
        requested_stake=10,
        confidence=0.90,
        spread=0.01,
        estimated_slippage=0,
        liquidity_usd=100_000,
        resolution_risk=ResolutionRisk.LOW,
    )
    decision = RiskDecision(
        approved=True,
        reasons=[],
        raw_edge=0.20,
        net_edge=0.19,
        approved_stake=10,
    )

    order = broker.submit(proposal, decision)

    assert order.quantity == pytest.approx(20)
    assert broker.cash == pytest.approx(990)
    assert broker.exposure == pytest.approx(10)
    assert broker.mark_to_market({"market-1:YES": 0.60}) == pytest.approx(1_002)
