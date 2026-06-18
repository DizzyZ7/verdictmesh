from verdictmesh.config import Settings
from verdictmesh.domain import (
    MarketSnapshot,
    PaperOrder,
    RiskContext,
    RiskDecision,
    TradeProposal,
    TradingMode,
)
from verdictmesh.market_data import GammaClient
from verdictmesh.paper import PaperBroker
from verdictmesh.risk import RiskEngine, RiskLimits


class VerdictMeshService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gamma = GammaClient(settings.gamma_api_url)
        self.paper = PaperBroker(settings.paper_starting_cash)
        self.risk = RiskEngine(
            RiskLimits(
                min_net_edge=settings.min_net_edge,
                min_confidence=settings.min_confidence,
                min_liquidity_usd=settings.min_liquidity_usd,
                max_spread=settings.max_spread,
                max_position_fraction=settings.max_position_fraction,
                max_total_exposure_fraction=settings.max_total_exposure_fraction,
                max_daily_loss_fraction=settings.max_daily_loss_fraction,
                live_trading_enabled=settings.live_trading_enabled,
            )
        )

    async def close(self) -> None:
        await self.gamma.close()

    async def scan_markets(self, limit: int | None = None) -> list[MarketSnapshot]:
        return await self.gamma.list_market_snapshots(
            limit=limit or self.settings.market_scan_limit
        )

    def evaluate(self, proposal: TradeProposal, context: RiskContext) -> RiskDecision:
        return self.risk.evaluate(proposal, context)

    def submit_paper_order(
        self,
        proposal: TradeProposal,
        *,
        daily_pnl: float = 0,
    ) -> tuple[RiskDecision, PaperOrder | None]:
        context = RiskContext(
            bankroll=self.settings.paper_starting_cash,
            current_exposure=self.paper.exposure,
            daily_pnl=daily_pnl,
            mode=TradingMode.PAPER,
        )
        decision = self.evaluate(proposal, context)
        if not decision.approved:
            return decision, None
        order = self.paper.submit(proposal, decision)
        return decision, order
