# VerdictMesh

[![CI](https://github.com/DizzyZ7/verdictmesh/actions/workflows/ci.yml/badge.svg)](https://github.com/DizzyZ7/verdictmesh/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.7.0-informational.svg)](https://github.com/DizzyZ7/verdictmesh/releases)
[![Trading mode](https://img.shields.io/badge/trading-paper%20only-orange.svg)](#project-status)

> **Consensus before capital.**

VerdictMesh is an autonomous prediction-market intelligence platform for evidence collection, probabilistic forecasting, deterministic risk control, paper trading, and full decision auditing.

The project follows a modular-monolith architecture. Market ingestion, evidence retrieval, forecasting agents, probability aggregation, risk evaluation, execution simulation, persistence, and observability are implemented as separate modules while remaining deployable as a single application.

## Table of contents

- [Project status](#project-status)
- [Core capabilities](#core-capabilities)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Operator authentication](#operator-authentication)
- [Local development](#local-development)
- [API overview](#api-overview)
- [Health and observability](#health-and-observability)
- [Forecast council](#forecast-council)
- [Risk controls](#risk-controls)
- [Historical order-book scanner](#historical-order-book-scanner)
- [Persistence and audit](#persistence-and-audit)
- [Quality checks](#quality-checks)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

## Project status

VerdictMesh currently operates in **paper-trading mode only**. Live execution is intentionally disabled until the platform has accumulated verifiable performance data, completed forecast calibration and replay testing, validated its risk controls, and confirmed platform availability for the operator's actual jurisdiction.

## Core capabilities

- FastAPI application with optional operator API-key authentication
- Active-market discovery through the Polymarket Gamma API
- Autonomous polling of public CLOB order books
- Full bid/ask depth persistence with deterministic state hashes
- Best bid, best ask, midpoint, spread, and available-notional calculations
- BUY and SELL fill simulation across order-book depth, including slippage and partial fills
- Autonomous evidence collection and ranking through the GDELT DOC API
- Evidence-grounded forecasting council with four independent Claude roles
- Schema-constrained JSON responses for every model output
- Deterministic probability consensus with disagreement, confidence intervals, and evidence coverage
- Fail-closed rejection when evidence is weak, uncertainty is excessive, or resolution rules are unclear
- Deterministic risk engine
- Paper broker with cash, position, and exposure accounting
- PostgreSQL audit trail for markets, evidence, forecasts, decisions, order books, and virtual orders
- Paper-portfolio recovery after process restarts
- Separate liveness and readiness probes
- Prometheus-compatible HTTP and runtime metrics
- Structured JSON logs with request IDs, normalized route templates, status codes, and latency
- Bounded retries for transient failures from idempotent upstream GET requests
- Alembic database migrations
- Non-root Docker image with an integrated health check
- Ruff, strict mypy, pytest, migration checks, Docker builds, and GitHub Actions CI

## Architecture

```text
Gamma API + CLOB order books + GDELT / external evidence sources
                              |
                              v
                  collection and normalization
                              |
                              v
                    historical persistence
                              |
                              v
                     candidate filtering
                              |
                              v
       researcher + domain expert + skeptic + resolution auditor
                              |
                              v
              deterministic probability consensus
                              |
                              v
                  deterministic risk engine
                              |
                              v
                 paper broker / execution adapter
                              |
                              v
        PostgreSQL audit + metrics + structured application logs
```

The language model never receives private trading credentials and cannot bypass the deterministic consensus or risk layers.

## Quick start

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

After startup:

| Service | URL |
|---|---|
| API | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| OpenAPI schema | `http://localhost:8000/openapi.json` |
| Liveness probe | `http://localhost:8000/health` |
| Readiness probe | `http://localhost:8000/ready` |

The API container applies Alembic migrations automatically. When `ORDER_BOOK_SCANNER_ENABLED=true`, historical order-book collection starts with the application.

Add `ANTHROPIC_API_KEY` to `.env` to run the live forecast council. The deterministic `/forecast/consensus` endpoint does not require an external model provider and can be used to test schemas and aggregation behavior.

## Operator authentication

When `OPERATOR_API_KEY` is configured, every operational endpoint requires the configured API-key header. The following endpoints remain public:

- `/health`
- `/ready`
- `/docs`
- `/redoc`
- `/openapi.json`

Recommended production configuration:

```env
APP_ENV=production
OPERATOR_API_KEY=<random-secret-with-at-least-32-characters>
OPERATOR_API_KEY_HEADER=X-API-Key
```

Generate a suitable secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example authenticated request:

```bash
curl -H "X-API-Key: $OPERATOR_API_KEY" http://localhost:8000/markets
```

The application fails fast during startup when `APP_ENV` is set to `production` or `staging` and no valid operator key is configured.

See [SECURITY.md](SECURITY.md) for the security policy and vulnerability-reporting guidance.

## Local development

VerdictMesh requires Python 3.12 or newer.

### Linux and macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn verdictmesh.api:app --reload
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn verdictmesh.api:app --reload
```

Without Docker, the default configuration uses a local SQLite database at `verdictmesh.db`. Docker Compose configures the application to use PostgreSQL 17.

## API overview

```text
GET  /health
GET  /ready
GET  /metrics
GET  /markets
POST /scanner/orderbooks
GET  /history/orderbooks/{asset_id}
POST /backtest/fill
POST /evidence/collect
GET  /evidence/packages
POST /forecast/consensus
POST /forecast/run
POST /forecast/auto
GET  /forecast/runs
POST /risk/evaluate
POST /paper/orders
GET  /paper/portfolio
GET  /audit/decisions
```

For `POST /backtest/fill`, the `amount` field represents USDC notional for a `BUY` request and outcome-token quantity for a `SELL` request.

Interactive request and response schemas are available through Swagger UI at `/docs`.

## Health and observability

### Liveness

`GET /health` is a lightweight liveness probe. It does not query PostgreSQL and only confirms that the process can serve HTTP requests.

### Readiness

`GET /ready` verifies database access and the state of the required background CLOB scanner. It returns HTTP 503 while the application is not ready to receive operational traffic.

### Metrics

`GET /metrics` returns Prometheus text format. The endpoint is protected by the operator key whenever authentication is enabled.

Available metrics include:

- HTTP request totals by method, normalized route template, and status
- request-duration count and sum
- in-flight request count
- process start timestamp
- CLOB scanner enabled and running states
- background scanner failure count
- timestamp of the last successful scanner cycle

Dynamic path values are not used as metric labels. For example, all order-book history requests are aggregated under `/history/orderbooks/{asset_id}` rather than by raw asset ID.

### Logging

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Structured request logs include `request_id`, `method`, `route`, `status_code`, `duration_ms`, and the client address. Use `LOG_FORMAT=text` for human-readable local-development logs.

## Forecast council

Each forecast is produced by four independent roles:

```text
researcher          collects facts, base rates, and direct evidence
domain_expert       applies domain knowledge and causal reasoning
skeptic             searches for counterarguments, bias, and hidden assumptions
resolution_auditor  verifies the exact market wording and resolution source
```

The current market price is intentionally withheld from the agents to reduce anchoring. After all responses are collected, deterministic application code calculates:

- final YES probability
- confidence interval
- disagreement across agents
- evidence coverage and quality
- resolution clarity
- raw edge relative to the market price
- explicit `NO TRADE` reasons

A forecast is rejected automatically when an agent references an unknown evidence ID, the resolution auditor is missing, evidence is insufficient, disagreement exceeds the configured threshold, or the estimated edge is too small.

Provider requests that may create a paid model inference are not retried automatically when provider acceptance is ambiguous. This avoids duplicate forecasts and duplicate costs. Idempotent Gamma, CLOB, and GDELT GET requests use bounded retries for transport failures, rate limiting, and transient server errors.

## Risk controls

Default limits:

```text
Minimum net edge:             7%
Minimum confidence:          70%
Minimum liquidity:      $10,000
Maximum spread:             2.5%
Maximum single position:      1% of bankroll
Maximum total exposure:      10% of bankroll
Maximum daily loss:           2% of bankroll
High resolution risk:      rejected
Live trading:              disabled
```

Risk decisions are deterministic and cannot be overridden by model output.

## Historical order-book scanner

```env
ORDER_BOOK_SCANNER_ENABLED=true
ORDER_BOOK_SCAN_INTERVAL_SECONDS=60
ORDER_BOOK_SCAN_CONCURRENCY=10
ORDER_BOOK_MARKET_LIMIT=50
ORDER_BOOK_ASSET_LIMIT=100
```

Identical order books are not persisted repeatedly. Uniqueness is determined by the combination of `asset_id` and the CLOB-provided `book_hash`.

## Persistence and audit

PostgreSQL stores:

- current market records
- market-price history
- complete historical order-book depth
- top-of-book values and calculated liquidity metrics
- evidence inputs and resolution rules
- model versions and each agent response
- final council forecasts and `NO TRADE` reasons
- risk-evaluation context
- approved and rejected decisions
- paper orders, positions, and virtual cash balances

A decision and its associated paper order are persisted in a single database transaction.

## Quality checks

Run the same core checks used by CI:

```bash
ruff check .
mypy src
pytest
DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic upgrade head
DATABASE_URL=sqlite+pysqlite:///./migration-test.db alembic downgrade base
docker build -t verdictmesh:local .
```

The GitHub Actions pipeline also validates installed dependencies and builds the production Docker image.

## Roadmap

1. WebSocket CLOB ingestion with snapshot and incremental-update reconstruction
2. Replay engine with latency, fees, spread, partial fills, and market resolution
3. Probability calibration, Brier Score tracking, and strategy attribution
4. Historical-data retention policies and archival workflows
5. Web dashboard and operational notifications
6. Isolated execution service with mandatory geoblock and jurisdiction checks

## Disclaimer

VerdictMesh is experimental software. Prediction markets can result in the complete loss of capital allocated to a position. The project does not guarantee profitability and must only be used where access to the underlying platform and trading activity are legally permitted.
