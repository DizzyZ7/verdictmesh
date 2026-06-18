import json
from typing import Any

import httpx

from verdictmesh.forecast_models import (
    AgentAnalysis,
    AgentForecast,
    AgentRole,
    ForecastRequest,
)

ROLE_INSTRUCTIONS: dict[AgentRole, str] = {
    AgentRole.RESEARCHER: (
        "Synthesize only the supplied evidence. Distinguish observed facts from "
        "assumptions, estimate a base rate, and abstain when the evidence is insufficient."
    ),
    AgentRole.DOMAIN_EXPERT: (
        "Analyze the event as a senior domain specialist. Use causal reasoning, base rates, "
        "timelines, and operational constraints while citing only supplied evidence IDs."
    ),
    AgentRole.SKEPTIC: (
        "Act as an adversarial forecaster. Search for disconfirming evidence, selection bias, "
        "stale information, hidden assumptions, and reasons the apparent thesis may fail."
    ),
    AgentRole.RESOLUTION_AUDITOR: (
        "Focus on the exact market wording, deadline, resolution source, edge cases, and the "
        "difference between real-world truth and the platform's formal resolution criteria."
    ),
}


class AnthropicForecastClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 2500,
        timeout_seconds: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key is required")
        self.model = model
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "user-agent": "VerdictMesh/0.4",
            },
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def analyze(
        self,
        request: ForecastRequest,
        role: AgentRole,
    ) -> AgentForecast:
        response = await self._client.post(
            "/v1/messages",
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": 0,
                "system": self._system_prompt(role),
                "messages": [
                    {
                        "role": "user",
                        "content": self._user_prompt(request),
                    }
                ],
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": AgentAnalysis.model_json_schema(),
                    }
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        text = self._extract_text(payload)
        analysis = AgentAnalysis.model_validate_json(text)
        return AgentForecast(
            **analysis.model_dump(),
            role=role,
            model_id=self.model,
        )

    @staticmethod
    def _system_prompt(role: AgentRole) -> str:
        return (
            "You are one independent member of a prediction-market forecasting council. "
            "Never invent sources or evidence IDs. Do not assume facts outside the supplied "
            "evidence. Produce a calibrated probability, explicitly identify uncertainty, "
            "and abstain when a defensible estimate is not possible. "
            + ROLE_INSTRUCTIONS[role]
        )

    @staticmethod
    def _user_prompt(request: ForecastRequest) -> str:
        evidence = [
            {
                "evidence_id": item.evidence_id,
                "title": item.title,
                "publisher": item.publisher,
                "published_at": (
                    item.published_at.isoformat() if item.published_at else None
                ),
                "authority_score": item.authority_score,
                "freshness_score": item.freshness_score,
                "excerpt": item.excerpt,
                "url": item.url,
            }
            for item in request.evidence
        ]
        context = {
            "market_id": request.market_id,
            "question": request.question,
            "category": request.category,
            "close_time": request.close_time.isoformat() if request.close_time else None,
            "resolution_rules": request.resolution_rules,
            "resolution_source": request.resolution_source,
            "evidence": evidence,
        }
        return (
            "Analyze the following market independently. The current market price is "
            "intentionally omitted to reduce anchoring. Return only the required structured "
            "forecast.\n\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _extract_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            raise ValueError("Claude API returned an unexpected payload")
        content = payload.get("content")
        if not isinstance(content, list):
            raise ValueError("Claude API response has no content blocks")
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                return str(block["text"])
        raise ValueError("Claude API response has no structured text block")
