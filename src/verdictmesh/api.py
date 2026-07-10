from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, PlainTextResponse

from verdictmesh import __version__
from verdictmesh.config import Settings, get_settings
from verdictmesh.domain import (
    DecisionAudit,
    FillEstimate,
    MarketSnapshot,
    OrderAction,
    OrderBookScanResult,
    OrderBookSnapshot,
    PaperOrder,
    RiskContext,
    RiskDecision,
    TradeProposal,
)
from verdictmesh.evidence_models import (
    EvidenceCollectionRequest,
    EvidenceCollectionResult,
    EvidencePackage,
)
from verdictmesh.forecast_models import (
    ConsensusRequest,
    CouncilForecast,
    ForecastRequest,
)
from verdictmesh.observability import (
    MetricsRegistry,
    configure_logging,
    install_observability_middleware,
)
from verdictmesh.security import install_security_middleware
from verdictmesh.service import VerdictMeshService


class PaperOrderRequest(BaseModel):
    proposal: TradeProposal
    daily_pnl: float = 0


class PaperOrderResponse(BaseModel):
    decision: RiskDecision
    order: PaperOrder | None


class FillSimulationRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    action: OrderAction
    amount: float = Field(gt=0)


class AutonomousForecastResponse(BaseModel):
    evidence: EvidenceCollectionResult
    forecast: CouncilForecast | None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = cast(Settings, app.state.settings)
    app.state.service = VerdictMeshService(settings)
    await app.state.service.start()
    try:
        yield
    finally:
        await app.state.service.close()


def create_app() -> FastAPI:
    resolved_settings = get_settings()
    configure_logging(resolved_settings.log_level, resolved_settings.log_format)
    metrics = MetricsRegistry()
    application = FastAPI(
        title="VerdictMesh API",
        version=__version__,
        description="Prediction-market intelligence and risk platform",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.metrics = metrics
    install_security_middleware(application, resolved_settings)
    install_observability_middleware(application, metrics)
    return application


app = create_app()


def get_service(request: Request) -> VerdictMeshService:
    return cast(VerdictMeshService, request.app.state.service)


def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_metrics_registry(request: Request) -> MetricsRegistry:
    return cast(MetricsRegistry, request.app.state.metrics)


ServiceDependency = Annotated[VerdictMeshService, Depends(get_service)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
MetricsDependency = Annotated[MetricsRegistry, Depends(get_metrics_registry)]


@app.get("/health")
def health(settings: SettingsDependency) -> dict[str, object]:
    """Liveness probe: confirms that the application process can serve HTTP."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.app_env,
        "operator_auth_enabled": settings.operator_auth_enabled,
        "trading_mode": settings.trading_mode,
        "live_trading_enabled": settings.live_trading_enabled,
    }


@app.get("/ready")
async def ready(service: ServiceDependency) -> JSONResponse:
    """Readiness probe: verifies database access and required background workers."""
    state = await service.readiness()
    status_code = 200 if state["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=state)


@app.get("/metrics", include_in_schema=False)
def metrics(
    service: ServiceDependency,
    registry: MetricsDependency,
) -> PlainTextResponse:
    payload = registry.render(service.operational_metrics())
    return PlainTextResponse(
        payload,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/markets")
async def markets(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MarketSnapshot]:
    try:
        return await service.scan_markets(limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Market data provider unavailable") from exc


@app.post("/scanner/orderbooks", response_model=OrderBookScanResult)
async def scan_orderbooks(
    service: ServiceDependency,
    market_limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> OrderBookScanResult:
    try:
        return await service.scan_order_books(market_limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Orderbook scan failed") from exc


@app.get("/history/orderbooks/{asset_id}")
def orderbook_history(
    asset_id: str,
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
) -> list[OrderBookSnapshot]:
    return service.order_book_history(asset_id, limit)


@app.post("/backtest/fill", response_model=FillEstimate)
def simulate_fill(
    payload: FillSimulationRequest,
    service: ServiceDependency,
) -> FillEstimate:
    estimate = service.estimate_historical_fill(
        payload.asset_id,
        payload.action,
        payload.amount,
    )
    if estimate is None:
        raise HTTPException(status_code=404, detail="No orderbook history for asset")
    return estimate


@app.post("/evidence/collect", response_model=EvidenceCollectionResult)
async def collect_evidence(
    payload: EvidenceCollectionRequest,
    service: ServiceDependency,
) -> EvidenceCollectionResult:
    try:
        return await service.collect_evidence(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Evidence collection failed") from exc


@app.get("/evidence/packages")
def evidence_packages(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EvidencePackage]:
    return service.recent_evidence_packages(limit)


@app.post("/forecast/consensus", response_model=CouncilForecast)
def forecast_consensus(
    payload: ConsensusRequest,
    service: ServiceDependency,
) -> CouncilForecast:
    try:
        return service.aggregate_forecast(payload.request, payload.agents)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/forecast/run", response_model=CouncilForecast)
async def run_forecast(
    payload: ForecastRequest,
    service: ServiceDependency,
) -> CouncilForecast:
    try:
        return await service.run_forecast(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Forecast council failed") from exc


@app.post("/forecast/auto", response_model=AutonomousForecastResponse)
async def autonomous_forecast(
    payload: EvidenceCollectionRequest,
    service: ServiceDependency,
) -> AutonomousForecastResponse:
    try:
        evidence_result, forecast = await service.run_autonomous_forecast(payload)
        return AutonomousForecastResponse(evidence=evidence_result, forecast=forecast)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Autonomous forecast failed") from exc


@app.get("/forecast/runs")
def forecast_runs(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CouncilForecast]:
    return service.recent_forecasts(limit)


@app.post("/risk/evaluate", response_model=RiskDecision)
def evaluate_risk(
    proposal: TradeProposal,
    context: RiskContext,
    service: ServiceDependency,
) -> RiskDecision:
    return service.evaluate_and_record(proposal, context)


@app.post("/paper/orders", response_model=PaperOrderResponse)
def submit_paper_order(
    payload: PaperOrderRequest,
    service: ServiceDependency,
) -> PaperOrderResponse:
    decision, order = service.submit_paper_order(
        payload.proposal,
        daily_pnl=payload.daily_pnl,
    )
    return PaperOrderResponse(decision=decision, order=order)


@app.get("/paper/portfolio")
def paper_portfolio(service: ServiceDependency) -> dict[str, object]:
    return service.paper.snapshot()


@app.get("/audit/decisions")
def audit_decisions(
    service: ServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DecisionAudit]:
    return service.recent_decisions(limit)
