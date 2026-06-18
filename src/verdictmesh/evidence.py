import hashlib
import math
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urlparse

from verdictmesh.evidence_models import (
    EvidenceCollectionRequest,
    EvidenceCollectionResult,
    EvidencePackage,
    EvidenceSourceCandidate,
)
from verdictmesh.forecast_models import EvidenceItem, ForecastRequest
from verdictmesh.gdelt import GdeltDocClient

STOPWORDS = {
    "will",
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "by",
    "before",
    "after",
    "during",
    "and",
    "or",
    "be",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "market",
    "event",
    "happen",
    "occur",
    "resolve",
    "end",
    "from",
    "with",
    "at",
    "as",
    "it",
    "its",
    "their",
    "his",
    "her",
}

HIGH_AUTHORITY_DOMAINS = {
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "bloomberg.com",
    "cnbc.com",
    "ec.europa.eu",
    "ft.com",
    "imf.org",
    "nytimes.com",
    "oecd.org",
    "reuters.com",
    "sec.gov",
    "un.org",
    "who.int",
    "worldbank.org",
    "wsj.com",
}

MEDIUM_AUTHORITY_SUFFIXES = (
    ".edu",
    ".gov",
    ".int",
    ".mil",
)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’-]{2,}")


def normalize_domain(domain: str) -> str:
    return domain.lower().strip().removeprefix("www.")


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def build_search_query(request: EvidenceCollectionRequest, *, max_terms: int) -> str:
    explicit_terms = [term.strip() for term in request.extra_queries if term.strip()]
    if explicit_terms:
        return " OR ".join(_quote_if_needed(term) for term in explicit_terms[:max_terms])

    words = [word.lower() for word in WORD_RE.findall(request.question)]
    selected: list[str] = []
    for word in words:
        if word in STOPWORDS or word in selected:
            continue
        selected.append(word)
        if len(selected) >= max_terms:
            break
    if not selected:
        compact = request.question.replace("?", "").strip()[:120]
        return _quote_if_needed(compact)
    if len(selected) <= 3:
        return " ".join(selected)
    return "(" + " OR ".join(selected) + ")"


def authority_score(domain: str, trusted_domains: Iterable[str] = ()) -> float:
    normalized = normalize_domain(domain)
    trusted = {normalize_domain(item) for item in trusted_domains}
    if normalized in trusted:
        return 1.0
    if normalized in HIGH_AUTHORITY_DOMAINS:
        return 0.92
    if any(normalized.endswith(suffix) for suffix in MEDIUM_AUTHORITY_SUFFIXES):
        return 0.86
    if normalized.endswith(".gov.uk") or normalized.endswith(".gov.au"):
        return 0.86
    if normalized.endswith(".org"):
        return 0.68
    return 0.55


def freshness_score(published_at: datetime | None, *, now: datetime) -> float:
    if published_at is None:
        return 0.45
    delta_days = max((now - published_at).total_seconds() / 86_400, 0.0)
    return max(0.15, math.exp(-delta_days / 21.0))


def keyword_overlap_score(question: str, candidate: EvidenceSourceCandidate) -> float:
    question_words = {
        word.lower()
        for word in WORD_RE.findall(question)
        if word.lower() not in STOPWORDS
    }
    if not question_words:
        return 0.0
    haystack = f"{candidate.title} {candidate.snippet}".lower()
    matches = sum(1 for word in question_words if word in haystack)
    return matches / len(question_words)


def candidate_score(
    request: EvidenceCollectionRequest,
    candidate: EvidenceSourceCandidate,
    *,
    now: datetime,
) -> float:
    return (
        authority_score(candidate.domain, request.trusted_domains) * 0.45
        + freshness_score(candidate.published_at, now=now) * 0.35
        + keyword_overlap_score(request.question, candidate) * 0.20
    )


def build_evidence_package(
    request: EvidenceCollectionRequest,
    *,
    query: str,
    provider: str,
    candidates: list[EvidenceSourceCandidate],
    max_items: int,
    min_items: int,
    now: datetime | None = None,
) -> EvidenceCollectionResult:
    current_time = now or datetime.now(UTC)
    seen_urls: set[str] = set()
    deduped: list[EvidenceSourceCandidate] = []
    rejected_urls: list[str] = []
    for candidate in candidates:
        normalized_url = normalize_url(candidate.url)
        if normalized_url in seen_urls:
            rejected_urls.append(candidate.url)
            continue
        seen_urls.add(normalized_url)
        deduped.append(candidate)

    ranked = sorted(
        deduped,
        key=lambda item: candidate_score(request, item, now=current_time),
        reverse=True,
    )
    evidence = [
        candidate_to_evidence(request, candidate, now=current_time)
        for candidate in ranked[:max_items]
    ]

    warnings: list[str] = []
    blockers: list[str] = []
    if len(evidence) < min_items:
        message = "Insufficient evidence collected"
        warnings.append(message)
        blockers.append(message)
    if not evidence:
        message = "No usable evidence returned by provider"
        warnings.append(message)
        blockers.append(message)

    package = EvidencePackage(
        market_id=request.market_id,
        query=query,
        provider=provider,
        candidates_found=len(candidates),
        evidence=evidence,
        rejected_urls=rejected_urls,
        warnings=warnings,
        created_at=current_time,
    )
    return EvidenceCollectionResult(
        package=package,
        forecast_ready=not blockers,
        forecast_blockers=blockers,
    )


def candidate_to_evidence(
    request: EvidenceCollectionRequest,
    candidate: EvidenceSourceCandidate,
    *,
    now: datetime,
) -> EvidenceItem:
    excerpt_parts = [candidate.title]
    if candidate.snippet:
        excerpt_parts.append(candidate.snippet)
    metadata = []
    if candidate.source_country:
        metadata.append(f"source_country={candidate.source_country}")
    if candidate.language:
        metadata.append(f"language={candidate.language}")
    if metadata:
        excerpt_parts.append("; ".join(metadata))

    return EvidenceItem(
        evidence_id=stable_evidence_id(candidate.url, candidate.title),
        url=candidate.url,
        title=candidate.title,
        publisher=candidate.publisher or candidate.domain,
        published_at=candidate.published_at,
        retrieved_at=now,
        excerpt="\n".join(excerpt_parts)[:5000],
        authority_score=authority_score(candidate.domain, request.trusted_domains),
        freshness_score=freshness_score(candidate.published_at, now=now),
    )


def package_to_forecast_request(
    request: EvidenceCollectionRequest,
    package: EvidencePackage,
) -> ForecastRequest:
    return ForecastRequest(
        market_id=request.market_id,
        question=request.question,
        resolution_rules=request.resolution_rules,
        resolution_source=request.resolution_source,
        category=request.category,
        market_price_yes=request.market_price_yes,
        close_time=request.close_time,
        evidence=package.evidence,
    )


def stable_evidence_id(url: str, title: str) -> str:
    digest = hashlib.sha256(f"{normalize_url(url)}|{title}".encode()).hexdigest()
    return f"ev_{digest[:16]}"


def _quote_if_needed(value: str) -> str:
    cleaned = value.strip().replace('"', "")
    if " " in cleaned:
        return f'"{cleaned}"'
    return cleaned


class EvidenceCollector:
    def __init__(
        self,
        client: GdeltDocClient,
        *,
        max_records: int,
        timespan: str,
        max_items: int,
        min_items: int,
        query_max_terms: int,
    ) -> None:
        self._client = client
        self._max_records = max_records
        self._timespan = timespan
        self._max_items = max_items
        self._min_items = min_items
        self._query_max_terms = query_max_terms

    async def collect(
        self,
        request: EvidenceCollectionRequest,
    ) -> EvidenceCollectionResult:
        query = build_search_query(request, max_terms=self._query_max_terms)
        candidates = await self._client.search_articles(
            query,
            max_records=self._max_records,
            timespan=self._timespan,
        )
        return build_evidence_package(
            request,
            query=query,
            provider="gdelt-doc",
            candidates=candidates,
            max_items=self._max_items,
            min_items=self._min_items,
        )
