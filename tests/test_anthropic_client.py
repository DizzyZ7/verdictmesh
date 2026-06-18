import json

import httpx
import pytest

from verdictmesh.anthropic_client import AnthropicForecastClient
from verdictmesh.forecast_models import AgentRole, EvidenceItem, ForecastRequest


@pytest.mark.asyncio
async def test_structured_forecast_request_omits_market_price() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/messages"
        assert payload["model"] == "claude-sonnet-4-6"
        assert payload["output_config"]["format"]["type"] == "json_schema"
        assert "market_price_yes" not in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "probability_yes": 0.64,
                                "confidence": 0.82,
                                "evidence_ids": ["e1"],
                                "counter_evidence_ids": [],
                                "assumptions": ["The official timetable remains valid"],
                                "risks": ["The event may be delayed"],
                                "resolution_clarity": 0.91,
                                "information_already_priced_in": False,
                                "abstain": False,
                                "abstain_reason": None,
                            }
                        ),
                    }
                ]
            },
        )

    client = AnthropicForecastClient(
        api_key="test-key",
        model="claude-sonnet-4-6",
        base_url="https://anthropic.example",
        transport=httpx.MockTransport(handler),
    )
    result = await client.analyze(
        ForecastRequest(
            market_id="market-1",
            question="Will the event happen?",
            resolution_rules="Official confirmation is required.",
            market_price_yes=0.41,
            evidence=[
                EvidenceItem(
                    evidence_id="e1",
                    url="https://official.example",
                    title="Official timetable",
                    excerpt="The event is scheduled.",
                    authority_score=0.9,
                    freshness_score=0.9,
                )
            ],
        ),
        AgentRole.RESEARCHER,
    )
    await client.close()

    assert result.role is AgentRole.RESEARCHER
    assert result.model_id == "claude-sonnet-4-6"
    assert result.probability_yes == pytest.approx(0.64)
    assert result.evidence_ids == ["e1"]
