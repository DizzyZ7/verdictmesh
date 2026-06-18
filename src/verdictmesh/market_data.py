import json
from collections.abc import Iterable
from typing import Any

import httpx

from verdictmesh.domain import MarketSnapshot


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


class GammaClient:
    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "VerdictMesh/0.1"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_active_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume_24hr",
    ) -> list[dict[str, Any]]:
        response = await self._client.get(
            "/events",
            params={
                "active": "true",
                "closed": "false",
                "limit": limit,
                "offset": offset,
                "order": order,
                "ascending": "false",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Gamma API returned an unexpected events payload")
        return [item for item in payload if isinstance(item, dict)]

    async def list_market_snapshots(self, *, limit: int = 100) -> list[MarketSnapshot]:
        events = await self.list_active_events(limit=limit)
        return normalize_markets(events)


def normalize_markets(events: Iterable[dict[str, Any]]) -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []
    for event in events:
        event_markets = event.get("markets")
        if not isinstance(event_markets, list):
            continue
        for market in event_markets:
            if not isinstance(market, dict):
                continue
            snapshot = _normalize_market(market, event)
            if snapshot is not None:
                snapshots.append(snapshot)
    return snapshots


def _normalize_market(
    market: dict[str, Any],
    event: dict[str, Any],
) -> MarketSnapshot | None:
    market_id = str(market.get("id") or market.get("conditionId") or "").strip()
    question = str(market.get("question") or event.get("title") or "").strip()
    if not market_id or not question:
        return None

    outcomes = [str(item).strip().upper() for item in _as_list(market.get("outcomes"))]
    prices = [_to_float(item, default=-1) for item in _as_list(market.get("outcomePrices"))]
    token_ids = [str(item) for item in _as_list(market.get("clobTokenIds"))]

    price_by_outcome = dict(zip(outcomes, prices, strict=False))
    token_by_outcome = dict(zip(outcomes, token_ids, strict=False))

    yes_price = price_by_outcome.get("YES")
    no_price = price_by_outcome.get("NO")
    if yes_price is not None and not 0 <= yes_price <= 1:
        yes_price = None
    if no_price is not None and not 0 <= no_price <= 1:
        no_price = None

    return MarketSnapshot(
        market_id=market_id,
        question=question,
        slug=market.get("slug") or event.get("slug"),
        condition_id=market.get("conditionId"),
        token_id_yes=token_by_outcome.get("YES"),
        token_id_no=token_by_outcome.get("NO"),
        price_yes=yes_price,
        price_no=no_price,
        liquidity_usd=_to_float(market.get("liquidityNum") or market.get("liquidity")),
        volume_24h_usd=_to_float(
            market.get("volume24hr") or market.get("volume24hrClob")
        ),
        active=bool(market.get("active", True)),
        closed=bool(market.get("closed", False)),
    )
