from pathlib import Path

from verdictmesh.forecast import aggregate_forecasts
from verdictmesh.forecast_models import (
    AgentForecast,
    AgentRole,
    EvidenceItem,
    ForecastRequest,
)
from verdictmesh.forecast_store import ForecastRepository


def database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_forecast_run_is_persisted_and_restored(tmp_path: Path) -> None:
    request = ForecastRequest(
        market_id="market-1",
        question="Will the event happen?",
        resolution_rules="Official confirmation is required.",
        market_price_yes=0.40,
        evidence=[
            EvidenceItem(
                evidence_id="e1",
                url="https://official.example/a",
                title="Official evidence",
                excerpt="The event is scheduled.",
                authority_score=0.90,
                freshness_score=0.90,
            ),
            EvidenceItem(
                evidence_id="e2",
                url="https://official.example/b",
                title="Independent evidence",
                excerpt="Preparations are complete.",
                authority_score=0.85,
                freshness_score=0.90,
            ),
        ],
    )
    agents = [
        AgentForecast(
            role=role,
            model_id="test-model",
            probability_yes=probability,
            confidence=0.85,
            evidence_ids=["e1", "e2"],
            resolution_clarity=0.90,
            information_already_priced_in=False,
        )
        for role, probability in (
            (AgentRole.RESEARCHER, 0.61),
            (AgentRole.DOMAIN_EXPERT, 0.63),
            (AgentRole.SKEPTIC, 0.57),
            (AgentRole.RESOLUTION_AUDITOR, 0.62),
        )
    ]
    forecast = aggregate_forecasts(request, agents)
    repository = ForecastRepository(database_url(tmp_path / "forecasts.db"))
    repository.create_schema()

    repository.record(request, forecast)
    restored = repository.recent()

    assert repository.count() == 1
    assert len(restored) == 1
    assert restored[0].run_id == forecast.run_id
    assert restored[0].probability_yes == forecast.probability_yes
    assert restored[0].agents[0].model_id == "test-model"
    repository.close()
