import asyncio
import logging
from contextlib import suppress
from threading import RLock

from verdictmesh.anthropic_client import AnthropicForecastClient
from verdictmesh.backtest import estimate_fill
from verdictmesh.clob import ClobClient
from verdictmesh.config import Settings
from verdictmesh.database import AuditRepository
from verdictmesh.domain import (
    DecisionAudit,
    FillEstimate,
    MarketSnapshot,
    OrderAction,
    OrderBookScanResult,
    OrderBookSnapshot,
    Outcome,
    PaperOrder,
    RiskContext,
    RiskDecision,
    TradeProposal,
    TradingMode,
)
from verdictmesh.evidence import EvidenceCollector, package_to_forecast_request
from verdictmesh.evidence_models import EvidenceCollectionRequest, EvidenceCollectionResult, EvidencePackage
from verdictmesh.evidence_store import EvidenceRepository
from verdictmesh.forecast import CouncilThresholds, ForecastCouncil
from verdictmesh.forecast import (
    aggregate_forecasts as aggregate_council_forecasts,
)
from verdictmesh.forecast_models import (
    AgentForecast,
    CouncilForecast,
    ForecastRequest,
)
from verdictmesh.forecast_store import ForecastRepository
from verdictmesh.gdelt import GdeltDocClient
from verdictmesh.history import HistoryRepository
from verdictmesh.market_data import GammaClient
from verdictmesh.paper import PaperBroker
from verdictmesh.risk import RiskEngine, RiskLimits

logger = logging.getLogger(__name__)


class VerdictMeshService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gamma = GammaClient(settings.gamma_api_url)
        self.clob = ClobClient(settings.clob_api_url)
        self.gdelt = GdeltDocClient(settings.gdelt_api_url)
        self.audit = AuditRepository(settings.database_url, echo=settings.database_echo)
        self.history = HistoryRepository(settings.database_url, echo=settings.database_echo)
        self.forecasts = ForecastRepository(
            settings.database_url,
            echo=settings.database_echo,
        )
        self.evidence_store = EvidenceRepository(
            settings.database_url,
            echo=settings.database_echo,
        )
        if settings.database_auto_create:
            self.audit.create_schema()
            self.history.create_schema()
            self.forecasts.create_schema()
            self.evidence_store.create_schema()

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
        self.evidence_collector = EvidenceCollector(
            self.gdelt,
            max_records=settings.evidence_search_max_records,
            timespan=settings.evidence_search_timespan,
            max_items=settings.evidence_max_items,
            min_items=settings.evidence_min_items,
            query_max_terms=settings.evidence_query_max_terms,
        )
        self.council_thresholds = CouncilThresholds(
            min_agents=settings.forecast_min_agents,
            min_evidence=settings.forecast_min_evidence,
            min_coverage=settings.forecast_min_coverage,
            min_evidence_quality=settings.forecast_min_evidence_quality,
            min_confidence=settings.forecast_min_confidence,
            max_disagreement=settings.forecast_max_disagreement,
            min_resolution_clarity=settings.forecast_min_resolution_clarity,
            min_actionable_edge=settings.forecast_min_actionable_edge,
        )
        self.anthropic: AnthropicForecastClient | None = None
        self.forecast_council: ForecastCouncil | None = None
        if settings.anthropic_api_key:
            self.anthropic = AnthropicForecastClient(
                api_key=settings.anthropic_api_key,
                model=settings.forecast_model,
                base_url=settings.anthropic_api_url,
                max_tokens=settings.forecast_max_tokens,
            )
            self.forecast_council = ForecastCouncil(
                self.anthropic,
                self.council_thresholds,
            )

        self._paper_lock = RLock()
        self._scanner_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self.settings.order_book_scanner_enabled and self._scanner_task is None:
            self._scanner_task = asyncio.create_task(
                self._scanner_loop(),
                name="verdictmesh-order-book-scanner",
            )

    async def close(self) -> None:
        if self._scanner_task is not None:
            self._scanner_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._scanner_task
            self._scanner_task = None
        await self.gamma.close()
        await self.clob.close()
        await self.gdelt.close()
        if self.anthropic is not None:
            await self.anthropic.close()
        self.audit.close()
        self.history.close()
        self.forecasts.close()
        self.evidence_store.close()

    async def scan_markets(self, limit: int | None = None) -> list[MarketSnapshot]:
        snapshots = await self.gamma.list_market_snapshots(
            limit=limit or self.settings.market_scan_limit
        )
        await asyncio.to_thread(self.audit.record_markets, snapshots)
        return snapshots

    async def scan_order_books(
        self,
        market_limit: int | None = None,
    ) -> OrderBookScanResult:
        markets = await self.scan_markets(
            market_limit or self.settings.order_book_market_limit
        )
        candidates: list[tuple[str, Outcome, str]] = []
        seen_assets: set[str] = set()
        for market in markets:
            for outcome, asset_id in (
                (Outcome.YES, market.token_id_yes),
                (Outcome.NO, market.token_id_no),
            ):
                if asset_id is None or asset_id in seen_assets:
                    continue
                seen_assets.add(asset_id)
                candidates.append((market.market_id, outcome, asset_id))
                if len(candidates) >= self.settings.order_book_asset_limit:
                    break
            if len(candidates) >= self.settings.order_book_asset_limit:
                break

        semaphore = asyncio.Semaphore(self.settings.order_book_scan_concurrency)

        async def fetch_one(
            candidate: tuple[str, Outcome, str],
        ) -> OrderBookSnapshot:
            app_market_id, outcome, asset_id = candidate
            async with semaphore:
                book = await self.clob.get_order_book(asset_id)
            return book.model_copy(
                update={"app_market_id": app_market_id, "outcome": outcome}
            )

        results = await asyncio.gather(
            *(fetch_one(candidate) for candidate in candidates),
            return_exceptions=True,
        )
        snapshots: list[OrderBookSnapshot] = []
        failures = 0
        for result in results:
            if isinstance(result, BaseException):
                failures += 1
                logger.warning("Orderbook fetch failed: %s", result)
            else:
                snapshots.append(result)

        inserted = await asyncio.to_thread(
            self.history.record_order_books,
            snapshots,
        )
        return OrderBookScanResult(
            markets_scanned=len(markets),
            assets_requested=len(candidates),
            snapshots_fetched=len(snapshots),
            snapshots_inserted=inserted,
            failures=failures,
        )

    def order_book_history(
        self,
        asset_id: str,
        limit: int = 100,
    ) -> list[OrderBookSnapshot]:
        return self.history.list_order_books(asset_id, limit)

    def estimate_historical_fill(
        self,
        asset_id: str,
        action: OrderAction,
        amount: float,
    ) -> FillEstimate | None:
        book = self.history.latest_order_book(asset_id)
        if book is None:
            return None
        return estimate_fill(book, action, amount)

    async def collect_evidence(
        self,
        request: EvidenceCollectionRequest,
    ) -> EvidenceCollectionResult:
        result = await self.evidence_collector.collect(request)
        await asyncio.to_thread(self.evidence_store.record, request, result.package)
        return result

    async def collect_forecast_request(
        self,
        request: EvidenceCollectionRequest,
    ) -> tuple[EvidenceCollectionResult, ForecastRequest | None]:
        result = await self.collect_evidence(request)
        if not result.forecast_ready:
            return result, None
        return result, package_to_forecast_request(request, result.package)

    async def run_autonomous_forecast(
        self,
        request: EvidenceCollectionRequest,
    ) -> tuple[EvidenceCollectionResult, CouncilForecast | None]:
        evidence_result, forecast_request = await self.collect_forecast_request(request)
        if forecast_request is None:
            return evidence_result, None
        forecast = await self.run_forecast(forecast_request)
        return evidence_result, forecast

    def recent_evidence_packages(self, limit: int = 100) -> list[EvidencePackage]:
        return self.evidence_store.recent(limit)

    def aggregate_forecast(
        self,
        request: ForecastRequest,
        agents: list[AgentForecast],
    ) -> CouncilForecast:
        forecast = aggregate_council_forecasts(
            request,
            agents,
            self.council_thresholds,
        )
        self.forecasts.record(request, forecast)
        return forecast

    async def run_forecast(self, request: ForecastRequest) -> CouncilForecast:
        if self.forecast_council is None:
            raise RuntimeError("Anthropic API key is not configured")
        forecast = await self.forecast_council.run(request)
        await asyncio.to_thread(self.forecasts.record, request, forecast)
        return forecast

    def recent_forecasts(self, limit: int = 100) -> list[CouncilForecast]:
        return self.forecasts.recent(limit)

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
        counts = self.audit.counts()
        counts["order_book_snapshots"] = self.history.count()
        counts["forecast_runs"] = self.forecasts.count()
        counts["evidence_packages"] = self.evidence_store.count()
        return counts

    async def _scanner_loop(self) -> None:
        while True:
            try:
                result = await self.scan_order_books()
                logger.info("Orderbook scan completed: %s", result.model_dump())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Autonomous orderbook scan failed")
            await asyncio.sleep(self.settings.order_book_scan_interval_seconds)
