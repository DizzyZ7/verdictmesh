from dataclasses import dataclass

from verdictmesh.domain import ResolutionRisk, RiskContext, RiskDecision, TradeProposal, TradingMode


@dataclass(frozen=True, slots=True)
class RiskLimits:
    min_net_edge: float = 0.07
    min_confidence: float = 0.70
    min_liquidity_usd: float = 10_000.0
    max_spread: float = 0.025
    max_position_fraction: float = 0.01
    max_total_exposure_fraction: float = 0.10
    max_daily_loss_fraction: float = 0.02
    live_trading_enabled: bool = False


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self._limits = limits

    def evaluate(self, proposal: TradeProposal, context: RiskContext) -> RiskDecision:
        reasons: list[str] = []

        if context.mode is TradingMode.LIVE and not self._limits.live_trading_enabled:
            reasons.append("Live trading is disabled")
        if proposal.net_edge < self._limits.min_net_edge:
            reasons.append("Net edge is below the minimum")
        if proposal.confidence < self._limits.min_confidence:
            reasons.append("Confidence is below the minimum")
        if proposal.liquidity_usd < self._limits.min_liquidity_usd:
            reasons.append("Liquidity is below the minimum")
        if proposal.spread > self._limits.max_spread:
            reasons.append("Spread exceeds the maximum")
        if proposal.resolution_risk is ResolutionRisk.HIGH:
            reasons.append("Resolution risk is high")

        daily_loss_limit = context.bankroll * self._limits.max_daily_loss_fraction
        if context.daily_pnl <= -daily_loss_limit:
            reasons.append("Daily loss limit has been reached")

        remaining_exposure = max(
            0.0,
            context.bankroll * self._limits.max_total_exposure_fraction
            - context.current_exposure,
        )
        position_cap = context.bankroll * self._limits.max_position_fraction
        approved_stake = min(proposal.requested_stake, position_cap, remaining_exposure)
        if approved_stake <= 0:
            reasons.append("No exposure capacity remains")

        approved = not reasons
        return RiskDecision(
            approved=approved,
            reasons=reasons,
            raw_edge=proposal.raw_edge,
            net_edge=proposal.net_edge,
            approved_stake=approved_stake if approved else 0.0,
        )
