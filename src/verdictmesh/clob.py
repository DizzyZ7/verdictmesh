from typing import Any

import httpx

from verdictmesh.domain import OrderBookLevel, OrderBookSnapshot


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_levels(value: Any, *, reverse: bool) -> list[OrderBookLevel]:
    if not isinstance(value, list):
        return []

    levels: list[OrderBookLevel] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        price = _to_float(item.get("price"))
        size = _to_float(item.get("size"))
        if price is None or size is None or not 0 < price < 1 or size < 0:
            continue
        levels.append(OrderBookLevel(price=price, size=size))
    return sorted(levels, key=lambda level: level.price, reverse=reverse)


class ClobClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "VerdictMesh/0.3"},
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_order_book(self, asset_id: str) -> OrderBookSnapshot:
        response = await self._client.get("/book", params={"token_id": asset_id})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("CLOB API returned an unexpected orderbook payload")

        condition_id = str(payload.get("market") or "").strip()
        returned_asset = str(payload.get("asset_id") or asset_id).strip()
        book_hash = str(payload.get("hash") or "").strip()
        if not condition_id or not returned_asset or not book_hash:
            raise ValueError("CLOB orderbook payload is missing identifiers")

        return OrderBookSnapshot(
            condition_id=condition_id,
            asset_id=returned_asset,
            source_timestamp=str(payload.get("timestamp") or "") or None,
            book_hash=book_hash,
            bids=_normalize_levels(payload.get("bids"), reverse=True),
            asks=_normalize_levels(payload.get("asks"), reverse=False),
            min_order_size=_to_float(payload.get("min_order_size")),
            tick_size=_to_float(payload.get("tick_size")),
            neg_risk=bool(payload.get("neg_risk", False)),
        )
