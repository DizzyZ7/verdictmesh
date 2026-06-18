from datetime import UTC, datetime, timedelta

import pytest

from verdictmesh.evidence import (
    authority_score,
    build_evidence_package,
    build_search_query,
    package_to_forecast_request,
)
from verdictmesh.evidence_models import EvidenceCollectionRequest, EvidenceSourceCandidate


def request() -> EvidenceCollectionRequest:
    return EvidenceCollectionRequest(
        market_id="market-1",
        question="Will ExampleCorp announce Project Atlas before July 2026?",
        resolution_rules="The announcement must be confirmed by the official source.",
        market_price_yes=0.44,
        trusted_domains=["official.example"],
    )


def test_query_builder_uses_distinct_market_terms() -> None:
    query = build_search_query(request(), max_terms=4)

    assert "examplecorp" in query
    assert "atlas" in query
    assert "will" not in query


def test_authority_score_prefers_trusted_and_official_domains() -> None:
    assert authority_score("official.example", ["official.example"]) == pytest.approx(1.0)
    assert authority_score("sec.gov") > authority_score("random-blog.example")


def test_evidence_package_deduplicates_and_builds_forecast_request() -> None:
    now = datetime.now(UTC)
    candidates = [
        EvidenceSourceCandidate(
            url="https://official.example/news/atlas?utm=1",
            title="Project Atlas remains scheduled",
            domain="official.example",
            publisher="Official Example",
            published_at=now - timedelta(days=1),
            snippet="The organization said the announcement remains on schedule.",
        ),
        EvidenceSourceCandidate(
            url="https://official.example/news/atlas?utm=2",
            title="Project Atlas remains scheduled",
            domain="official.example",
            publisher="Official Example",
            published_at=now - timedelta(days=1),
            snippet="Duplicate URL with different tracking parameters.",
        ),
        EvidenceSourceCandidate(
            url="https://reuters.com/technology/examplecorp-atlas",
            title="ExampleCorp prepares Project Atlas announcement",
            domain="reuters.com",
            publisher="Reuters",
            published_at=now - timedelta(days=2),
            snippet="Preparations are under way according to officials.",
        ),
    ]

    result = build_evidence_package(
        request(),
        query="examplecorp atlas announcement",
        provider="test",
        candidates=candidates,
        max_items=5,
        min_items=2,
        now=now,
    )
    forecast_request = package_to_forecast_request(request(), result.package)

    assert result.forecast_ready is True
    assert result.package.candidates_found == 3
    assert len(result.package.evidence) == 2
    assert len(result.package.rejected_urls) == 1
    assert forecast_request.evidence == result.package.evidence
