import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter, time
from typing import Any, Literal

from fastapi import FastAPI, Request
from starlette.responses import Response

type CallNext = Callable[[Request], Awaitable[Response]]
type MetricKey = tuple[str, str, int]

logger = logging.getLogger("verdictmesh.http")


@dataclass
class RequestMetric:
    count: int = 0
    duration_seconds: float = 0.0


class MetricsRegistry:
    """Small dependency-free Prometheus registry for process and HTTP metrics."""

    def __init__(self) -> None:
        self._started_at = time()
        self._requests: dict[MetricKey, RequestMetric] = {}
        self._in_flight = 0
        self._lock = Lock()

    def request_started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def request_finished(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        key = (method, route, status_code)
        with self._lock:
            metric = self._requests.setdefault(key, RequestMetric())
            metric.count += 1
            metric.duration_seconds += duration_seconds
            self._in_flight = max(0, self._in_flight - 1)

    def render(self, gauges: Mapping[str, float] | None = None) -> str:
        with self._lock:
            requests = {
                key: RequestMetric(value.count, value.duration_seconds)
                for key, value in self._requests.items()
            }
            in_flight = self._in_flight

        lines = [
            "# HELP verdictmesh_process_start_time_seconds Unix timestamp when the process started.",
            "# TYPE verdictmesh_process_start_time_seconds gauge",
            f"verdictmesh_process_start_time_seconds {self._started_at:.6f}",
            "# HELP verdictmesh_http_requests_in_flight Current HTTP requests being processed.",
            "# TYPE verdictmesh_http_requests_in_flight gauge",
            f"verdictmesh_http_requests_in_flight {in_flight}",
            "# HELP verdictmesh_http_requests_total Completed HTTP requests.",
            "# TYPE verdictmesh_http_requests_total counter",
        ]

        for (method, route, status_code), metric in sorted(requests.items()):
            labels = _labels(method=method, route=route, status=str(status_code))
            lines.append(f"verdictmesh_http_requests_total{labels} {metric.count}")

        lines.extend(
            [
                "# HELP verdictmesh_http_request_duration_seconds_sum Total request duration.",
                "# TYPE verdictmesh_http_request_duration_seconds_sum counter",
            ]
        )
        for (method, route, status_code), metric in sorted(requests.items()):
            labels = _labels(method=method, route=route, status=str(status_code))
            lines.append(
                "verdictmesh_http_request_duration_seconds_sum"
                f"{labels} {metric.duration_seconds:.9f}"
            )

        lines.extend(
            [
                "# HELP verdictmesh_http_request_duration_seconds_count Number of timed requests.",
                "# TYPE verdictmesh_http_request_duration_seconds_count counter",
            ]
        )
        for (method, route, status_code), metric in sorted(requests.items()):
            labels = _labels(method=method, route=route, status=str(status_code))
            lines.append(
                f"verdictmesh_http_request_duration_seconds_count{labels} {metric.count}"
            )

        if gauges:
            for name, value in sorted(gauges.items()):
                lines.extend(
                    [
                        f"# TYPE {name} gauge",
                        f"{name} {value:.6f}",
                    ]
                )

        return "\n".join(lines) + "\n"


class JsonLogFormatter(logging.Formatter):
    """Serialize application logs as one JSON object per line."""

    _EXTRA_FIELDS = (
        "request_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
        "client",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def configure_logging(level: str, log_format: Literal["text", "json"]) -> None:
    normalized_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(normalized_level)


def install_observability_middleware(app: FastAPI, registry: MetricsRegistry) -> None:
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next: CallNext) -> Response:
        registry.request_started()
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = perf_counter() - started
            route = _route_template(request, fallback="__error__")
            registry.request_finished(
                method=request.method,
                route=route,
                status_code=500,
                duration_seconds=duration,
            )
            logger.exception(
                "http_request_failed",
                extra=_request_log_fields(request, route, 500, duration),
            )
            raise

        duration = perf_counter() - started
        route = _route_template(request, fallback="__unmatched__")
        registry.request_finished(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_seconds=duration,
        )
        logger.info(
            "http_request_completed",
            extra=_request_log_fields(request, route, response.status_code, duration),
        )
        return response


def _route_template(request: Request, *, fallback: str) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else fallback


def _request_log_fields(
    request: Request,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> dict[str, object]:
    client = request.client.host if request.client is not None else None
    return {
        "request_id": getattr(request.state, "request_id", None),
        "method": request.method,
        "route": route,
        "status_code": status_code,
        "duration_ms": round(duration_seconds * 1000, 3),
        "client": client,
    }


def _labels(**values: str) -> str:
    rendered = ",".join(
        f'{name}="{_escape_label(value)}"' for name, value in sorted(values.items())
    )
    return "{" + rendered + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
