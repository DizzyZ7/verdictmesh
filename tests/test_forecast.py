import pytest

from verdictmesh.forecast import aggregate_forecasts
from verdictmesh.forecast_models import (
    AgentForecast,
    AgentRole,
    EvidenceItem,
    ForecastRequest,
    PreferredSide,
)


def forecast_request() -> ForecastRequest:
    return ForecastRequest(
        market_id="market-1",
        question="Will the event happen?",
        resolution_rules="The official source must confirm the event before the deadline.",
        market_price_yes=0.40,
        evidence=[
            EvidenceItem(
                evidence_id="e1",
                url="https://official.example/report",
                title="Official report",
                publisher="Official source",
                excerpt="The event remains on schedule.",
                authority_score=0.90,
                freshness_score=0.90,
            ),
            EvidenceItem(
                evidence_id="e2",
                url="https://statistics.example/data",
                title="Historical data",
                publisher="Statistics office",
                excerpt="Comparable events completed in 70 percent of cases.",
                authority_score=0.80,
                freshness_score=0.90,
            ),
        ],
    )


def agent(role: AgentRole, probability: float) -> AgentForecast:
    return AgentForecast(
        role=role,
        model_id="test-model",
        probability_yes=probability,
        confidence=0.85,
        evidence_ids=["e1", "e2"],
        counter_evidence_ids=[],
        assumptions=[],
        risks=[],
        resolution_clarity=0.90,
        information_already_priced_in=False,
    )


def test_consistent_council_allows_actionable_forecast() -> None:
    result = aggregate_forecasts(
        forecast_request(),
        [
            agent(AgentRole.RESEARCHER, 0.60),
            agent(AgentRole.DOMAIN_EXPERT, 0.62),
            agent(AgentRole.SKEPTIC, 0.56),
            agent(AgentRole.RESOLUTION_AUDITOR, 0.61),
        ],
    )

    assert result.trade_allowed is True
    assert result.preferred_side is PreferredSide.YES
    assert result.raw_edge > 0.15
    assert result.disagreement < 0.15
    assert result.evidence_coverage == 1


def test_unknown_evidence_reference_fails_closed() -> None:
    invalid = agent(AgentRole.RESEARCHER, 0.60).model_copy(
        update={"evidence_ids": ["unknown"]}
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        aggregate_forecasts(forecast_request(), [invalid])


def test_high_agent_disagreement_blocks_trade() -> None:
    result = aggregate_forecasts(
        forecast_request(),
        [
            agent(AgentRole.RESEARCHER, 0.95),
            agent(AgentRole.DOMAIN_EXPERT, 0.10),
            agent(AgentRole.SKEPTIC, 0.90),
            agent(AgentRole.RESOLUTION_AUDITOR, 0.10),
        ],
    )

    assert result.trade_allowed is False
    assert "Agent disagreement is too high" in result.no_trade_reasons
