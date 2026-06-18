import asyncio
import math
from dataclasses import dataclass
from typing import Protocol

from verdictmesh.forecast_models import (
    AgentForecast,
    AgentRole,
    CouncilForecast,
    ForecastRequest,
    PreferredSide,
)

ROLE_WEIGHTS: dict[AgentRole, float] = {
    AgentRole.RESEARCHER: 0.25,
    AgentRole.DOMAIN_EXPERT: 0.35,
    AgentRole.SKEPTIC: 0.20,
    AgentRole.RESOLUTION_AUDITOR: 0.20,
}


@dataclass(frozen=True, slots=True)
class CouncilThresholds:
    min_agents: int = 3
    min_evidence: int = 2
    min_coverage: float = 0.50
    min_evidence_quality: float = 0.55
    min_confidence: float = 0.65
    max_disagreement: float = 0.15
    min_resolution_clarity: float = 0.75
    min_actionable_edge: float = 0.07


DEFAULT_COUNCIL_THRESHOLDS = CouncilThresholds()


class ForecastAgentClient(Protocol):
    async def analyze(
        self,
        request: ForecastRequest,
        role: AgentRole,
    ) -> AgentForecast: ...


def aggregate_forecasts(
    request: ForecastRequest,
    agents: list[AgentForecast],
    thresholds: CouncilThresholds = DEFAULT_COUNCIL_THRESHOLDS,
) -> CouncilForecast:
    if not agents:
        raise ValueError("at least one agent forecast is required")

    roles = [agent.role for agent in agents]
    if len(roles) != len(set(roles)):
        raise ValueError("agent roles must be unique")

    evidence_by_id = {item.evidence_id: item for item in request.evidence}
    all_references: set[str] = set()
    for agent in agents:
        references = set(agent.evidence_ids) | set(agent.counter_evidence_ids)
        unknown = references - evidence_by_id.keys()
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"agent references unknown evidence: {names}")
        all_references.update(references)

    active_agents = [agent for agent in agents if not agent.abstain]
    weighted_agents = [
        (agent, ROLE_WEIGHTS[agent.role] * max(agent.confidence, 0.05))
        for agent in active_agents
    ]
    total_weight = sum(weight for _, weight in weighted_agents)
    if total_weight <= 0:
        raise ValueError("agent weights must be positive")

    probability_yes = sum(
        agent.probability_yes * weight for agent, weight in weighted_agents
    ) / total_weight
    confidence = sum(
        agent.confidence * weight for agent, weight in weighted_agents
    ) / total_weight
    resolution_clarity = sum(
        agent.resolution_clarity * weight for agent, weight in weighted_agents
    ) / total_weight
    variance = sum(
        weight * (agent.probability_yes - probability_yes) ** 2
        for agent, weight in weighted_agents
    ) / total_weight
    disagreement = math.sqrt(variance)

    interval = max(0.05, 1.96 * disagreement)
    evidence_coverage = (
        len(all_references) / len(request.evidence) if request.evidence else 0.0
    )
    referenced_evidence = [evidence_by_id[item_id] for item_id in all_references]
    average_evidence_quality = (
        sum(
            item.authority_score * item.freshness_score
            for item in referenced_evidence
        )
        / len(referenced_evidence)
        if referenced_evidence
        else 0.0
    )
    raw_edge = probability_yes - request.market_price_yes

    no_trade_reasons: list[str] = []
    if len(active_agents) < thresholds.min_agents:
        no_trade_reasons.append("Insufficient independent agent forecasts")
    resolution_auditor = next(
        (
            agent
            for agent in agents
            if agent.role is AgentRole.RESOLUTION_AUDITOR
        ),
        None,
    )
    if resolution_auditor is None or resolution_auditor.abstain:
        no_trade_reasons.append("Resolution auditor is missing or abstained")
    if len(request.evidence) < thresholds.min_evidence:
        no_trade_reasons.append("Insufficient evidence")
    if evidence_coverage < thresholds.min_coverage:
        no_trade_reasons.append("Evidence coverage is too low")
    if average_evidence_quality < thresholds.min_evidence_quality:
        no_trade_reasons.append("Evidence quality is too low")
    if confidence < thresholds.min_confidence:
        no_trade_reasons.append("Council confidence is too low")
    if disagreement > thresholds.max_disagreement:
        no_trade_reasons.append("Agent disagreement is too high")
    if resolution_clarity < thresholds.min_resolution_clarity:
        no_trade_reasons.append("Resolution clarity is too low")
    if abs(raw_edge) < thresholds.min_actionable_edge:
        no_trade_reasons.append("Forecast edge is below the actionable threshold")

    return CouncilForecast(
        market_id=request.market_id,
        market_price_yes=request.market_price_yes,
        probability_yes=probability_yes,
        lower_bound=max(0.0, probability_yes - interval),
        upper_bound=min(1.0, probability_yes + interval),
        confidence=confidence,
        disagreement=disagreement,
        evidence_coverage=evidence_coverage,
        resolution_clarity=resolution_clarity,
        average_evidence_quality=average_evidence_quality,
        raw_edge=raw_edge,
        preferred_side=(
            PreferredSide.YES if raw_edge >= 0 else PreferredSide.NO
        ),
        trade_allowed=not no_trade_reasons,
        no_trade_reasons=no_trade_reasons,
        agents=agents,
    )


class ForecastCouncil:
    def __init__(
        self,
        client: ForecastAgentClient,
        thresholds: CouncilThresholds,
    ) -> None:
        self._client = client
        self._thresholds = thresholds

    async def run(self, request: ForecastRequest) -> CouncilForecast:
        roles = list(AgentRole)
        results = await asyncio.gather(
            *(self._client.analyze(request, role) for role in roles),
            return_exceptions=True,
        )
        agents: list[AgentForecast] = []
        errors: list[str] = []
        for role, result in zip(roles, results, strict=True):
            if isinstance(result, BaseException):
                errors.append(f"{role.value}: {result}")
            else:
                agents.append(result)

        if len(agents) < self._thresholds.min_agents:
            details = "; ".join(errors) or "unknown agent failures"
            raise RuntimeError(f"forecast council failed closed: {details}")
        return aggregate_forecasts(request, agents, self._thresholds)
