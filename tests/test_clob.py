import httpx
import pytest

from verdictmesh.clob import ClobClient


@pytest.mark.asyncio
async def test_get_order_book_normalizes_levels() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/book"
        assert request.url.params["token_id"] == "asset-1"
        return httpx.Response(
            200,
            json={
                "market": "condition-1",
                "asset_id": "asset-1",
                "timestamp": "1757908892351",
                "bids": [
                    {"price": "0.47", "size": "20"},
                    {"price": "0.48", "size": "10"},
                ],
                "asks": [
                    {"price": "0.54", "size": "10"},
                    {"price": "0.52", "size": "5"},
                ],
                "min_order_size": "5",
                "tick_size": "0.01",
                "neg_risk": False,
                "hash": "hash-1",
            },
        )

    client = ClobClient(
        "https://clob.example",
        transport=httpx.MockTransport(handler),
    )
    book = await client.get_order_book("asset-1")
    await client.close()

    assert book.best_bid == pytest.approx(0.48)
    assert book.best_ask == pytest.approx(0.52)
    assert book.midpoint == pytest.approx(0.50)
    assert book.spread == pytest.approx(0.04)
    assert book.bids[0].price == pytest.approx(0.48)
    assert book.asks[0].price == pytest.approx(0.52)
