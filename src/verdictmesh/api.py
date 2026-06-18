from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.service = VerdictMeshService(settings)
    await app.state.service.start()
    try:
        yield
    finally:
        await app.state.service.close()


def create_app() -> FastAPI:
    return FastAPI(
        title="VerdictMesh API",
        version="0.3.0",
        description="Prediction-market intelligence and risk platform",
        lifespan=lifespan,
    )


app = create_app()


def get_service(request: Request) -> VerdictMeshService:
    return cast(VerdictMeshService, request.app.state.service)


ServiceDependency = Annotated[VerdictMeshService, Depends(get_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@app.get("/health")
def health(
    settings: SettingsDependency,
    service: ServiceDependency,
) -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "trading_mode": settings.trading_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "order_book_scanner_enabled": settings.order_book_scanner_enabled,
        "audit": service.audit_counts(),
    }


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
