# VerdictMesh

> Consensus before capital.

VerdictMesh is an autonomous, multi-agent prediction-market research and execution platform. It is designed around a strict separation of responsibilities: data collection, evidence gathering, probability estimation, adversarial review, deterministic risk checks and order execution.

## Current phase

The first milestone is intentionally **paper-trading only**. Live execution remains hard-disabled until the following are proven with recorded data:

- reliable market-data ingestion;
- calibrated probability estimates;
- deterministic risk controls;
- complete audit logging;
- jurisdiction and platform-availability checks;
- positive results after spread and slippage assumptions.

## Included in this bootstrap

- FastAPI service;
- active Polymarket event and market discovery through the Gamma API;
- normalized market snapshots;
- deterministic trade-risk evaluation;
- in-memory paper broker and portfolio accounting;
- Docker image and local Compose configuration;
- unit tests and GitHub Actions CI.

## Architecture

```text
Market data -> candidate filter -> analyst agents -> adversarial review
            -> probability consensus -> deterministic risk engine
            -> paper/live execution adapter -> audit and monitoring
```

No language model is allowed to access a wallet key or bypass the risk engine.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8000/docs`.

Local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn verdictmesh.api:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn verdictmesh.api:app --reload
```

## Initial API

- `GET /health` - service state and trading mode;
- `GET /markets` - normalized active market snapshots;
- `POST /risk/evaluate` - deterministic assessment of a proposed trade;
- `POST /paper/orders` - risk-check and submit a paper order;
- `GET /paper/portfolio` - paper cash, positions and orders.

## Safety defaults

- paper mode is enabled;
- live trading is disabled;
- one position is capped at 1% of bankroll;
- total exposure is capped at 10% of bankroll;
- high resolution risk is rejected;
- weak edge, confidence, liquidity or spread is rejected;
- reaching the daily loss limit blocks new trades.

These defaults are starting controls, not a promise of profitability.

## Roadmap

1. Persistent PostgreSQL audit log.
2. Historical snapshots and backtesting.
3. Source collection and evidence ranking.
4. Multi-agent Claude research council.
5. Calibration, Brier score and strategy attribution.
6. Web dashboard and operational alerts.
7. Isolated execution service with a mandatory geoblock check.

## Disclaimer

VerdictMesh is experimental software. Prediction-market trading can lose the entire amount committed to a position. The software does not guarantee profit and must only be operated where access and trading are lawful.
