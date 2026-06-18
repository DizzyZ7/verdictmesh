from pathlib import Path

from verdictmesh.evidence import build_evidence_package
from verdictmesh.evidence_models import EvidenceCollectionRequest, EvidenceSourceCandidate
from verdictmesh.evidence_store import EvidenceRepository


def database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_evidence_package_is_persisted_and_restored(tmp_path: Path) -> None:
    request = EvidenceCollectionRequest(
        market_id="market-1",
        question="Will ExampleCorp announce Project Atlas?",
        resolution_rules="Official confirmation is required.",
        market_price_yes=0.42,
    )
    result = build_evidence_package(
        request,
        query="examplecorp atlas",
        provider="test",
        candidates=[
            EvidenceSourceCandidate(
                url="https://news.example/story",
                title="ExampleCorp prepares Project Atlas",
                domain="news.example",
                publisher="Example News",
                snippet="The announcement is expected soon.",
            )
        ],
        max_items=5,
        min_items=1,
    )
    repository = EvidenceRepository(database_url(tmp_path / "evidence.db"))
    repository.create_schema()

    repository.record(request, result.package)
    restored = repository.recent()

    assert repository.count() == 1
    assert len(restored) == 1
    assert restored[0].package_id == result.package.package_id
    assert restored[0].evidence[0].title == "ExampleCorp prepares Project Atlas"
    repository.close()
