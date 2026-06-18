import httpx
import pytest

from verdictmesh.gdelt import GDELT_DOC_PATH, GdeltDocClient


@pytest.mark.asyncio
async def test_gdelt_client_parses_article_list() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == GDELT_DOC_PATH
        assert request.url.params["mode"] == "artlist"
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "url": "https://news.example/story",
                        "title": "Example story",
                        "domain": "news.example",
                        "seendate": "20260618T170000Z",
                        "language": "English",
                        "sourcecountry": "United States",
                        "snippet": "A useful article snippet.",
                        "socialimage": "https://news.example/image.jpg",
                    },
                    {"url": "", "title": "Invalid story"},
                ]
            },
        )

    client = GdeltDocClient(
        "https://gdelt.example",
        transport=httpx.MockTransport(handler),
    )
    articles = await client.search_articles(
        "example query",
        max_records=10,
        timespan="1week",
    )
    await client.close()

    assert len(articles) == 1
    assert articles[0].url == "https://news.example/story"
    assert articles[0].domain == "news.example"
    assert articles[0].published_at is not None
    assert articles[0].snippet == "A useful article snippet."
