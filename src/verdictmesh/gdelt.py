from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from verdictmesh.evidence_models import EvidenceSourceCandidate

GDELT_DOC_PATH = "/".join(("", "api", "v2", "doc", "doc"))


def parse_gdelt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


class GdeltDocClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "VerdictMesh/0.5"},
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_articles(
        self,
        query: str,
        *,
        max_records: int,
        timespan: str,
        sort: str = "HybridRel",
    ) -> list[EvidenceSourceCandidate]:
        response = await self._client.get(
            GDELT_DOC_PATH,
            params={
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_records,
                "timespan": timespan,
                "sort": sort,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("GDELT returned an unexpected payload")
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            raise ValueError("GDELT payload has no article list")

        candidates: list[EvidenceSourceCandidate] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            try:
                candidates.append(self._parse_article(article))
            except ValueError:
                continue
        return candidates

    @staticmethod
    def _parse_article(article: dict[str, Any]) -> EvidenceSourceCandidate:
        url = str(article.get("url") or "").strip()
        title = str(article.get("title") or "").strip()
        if not url or not title:
            raise ValueError("GDELT article is missing url or title")
        domain = str(article.get("domain") or domain_from_url(url)).strip().lower()
        image_url = article.get("socialimage")
        return EvidenceSourceCandidate(
            url=url,
            title=title,
            domain=domain.removeprefix("www."),
            publisher=domain.removeprefix("www."),
            published_at=parse_gdelt_datetime(str(article.get("seendate") or "")),
            language=str(article.get("language") or "").strip(),
            source_country=str(article.get("sourcecountry") or "").strip(),
            snippet=str(article.get("snippet") or article.get("description") or "").strip(),
            image_url=str(image_url).strip() if image_url else None,
        )
