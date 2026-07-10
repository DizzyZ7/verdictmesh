import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from verdictmesh.observability import (
    JsonLogFormatter,
    MetricsRegistry,
    install_observability_middleware,
)


def test_observability_middleware_uses_route_templates() -> None:
    app = FastAPI()
    registry = MetricsRegistry()
    install_observability_middleware(app, registry)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    client = TestClient(app)

    response = client.get("/items/sensitive-dynamic-id")
    metrics = registry.render()

    assert response.status_code == 200
    assert 'route="/items/{item_id}"' in metrics
    assert "sensitive-dynamic-id" not in metrics
    assert 'status="200"' in metrics
    assert "verdictmesh_http_requests_in_flight 0" in metrics


def test_metrics_registry_renders_runtime_gauges() -> None:
    registry = MetricsRegistry()
    registry.request_started()
    registry.request_finished(
        method="POST",
        route="/forecast/run",
        status_code=503,
        duration_seconds=0.25,
    )

    metrics = registry.render({"verdictmesh_orderbook_scanner_running": 1.0})

    assert (
        'verdictmesh_http_requests_total{method="POST",route="/forecast/run",status="503"} 1'
        in metrics
    )
    assert "verdictmesh_orderbook_scanner_running 1.000000" in metrics
    assert "verdictmesh_http_request_duration_seconds_sum" in metrics


def test_json_log_formatter_emits_machine_readable_context() -> None:
    record = logging.LogRecord(
        name="verdictmesh.http",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request_completed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-123"
    record.method = "GET"
    record.route = "/health"
    record.status_code = 200
    record.duration_ms = 1.5

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "http_request_completed"
    assert payload["request_id"] == "request-123"
    assert payload["route"] == "/health"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.5
