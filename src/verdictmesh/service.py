import asyncio
from threading import RLock

from verdictmesh.config import Settings
from verdictmesh.database import AuditRepository
from verdictmesh.domain import (
    DecisionAudit,
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
        self.audit = AuditRepository(settings.database_url, echo=settings.database_echo)
        if settings.database_auto_create:
            self.audit.create_schema()
        state = self.audit.initialize_portfolio(settings.paper_starting_cash)
        self.paper = PaperBroker.restore(
            starting_cash=state.starting_cash,
            cash=state.cash,
            orders=state.orders,
            positions=state.positions,
        )
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
        self._paper_lock = RLock()

    async def close(self) -> None:
        await self.gamma.close()
        self.audit.close()

    async def scan_markets(self, limit: int | None = None) -> list[MarketSnapshot]:
        snapshots = await self.gamma.list_market_snapshots(
            limit=limit or self.settings.market_scan_limit
        )
        await asyncio.to_thread(self.audit.record_markets, snapshots)
        return snapshots

    def evaluate(self, proposal: TradeProposal, context: RiskContext) -> RiskDecision:
        return self.risk.evaluate(proposal, context)

    def evaluate_and_record(
        self,
        proposal: TradeProposal,
        context: RiskContext,
    ) -> RiskDecision:
        decision = self.evaluate(proposal, context)
        self.audit.record_decision(proposal, context, decision)
        return decision

    def submit_paper_order(
        self,
        proposal: TradeProposal,
        *,
        daily_pnl: float = 0,
    ) -> tuple[RiskDecision, PaperOrder | None]:
        with self._paper_lock:
            context = RiskContext(
                bankroll=self.paper.starting_cash,
                current_exposure=self.paper.exposure,
                daily_pnl=daily_pnl,
                mode=TradingMode.PAPER,
            )
            decision = self.evaluate(proposal, context)
            if not decision.approved:
                self.audit.record_decision(proposal, context, decision)
                return decision, None

            order = self.paper.prepare_order(proposal, decision)
            position = self.paper.projected_position(order)
            resulting_cash = self.paper.cash - order.stake
            self.audit.commit_paper_order(
                proposal=proposal,
                context=context,
                decision=decision,
                order=order,
                resulting_cash=resulting_cash,
                resulting_position=position,
            )
            self.paper.apply_order(order)
            return decision, order

    def recent_decisions(self, limit: int = 100) -> list[DecisionAudit]:
        return self.audit.recent_decisions(limit)

    def audit_counts(self) -> dict[str, int]:
        return self.audit.counts()
