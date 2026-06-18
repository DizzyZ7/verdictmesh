"""Create evidence-grounded forecast run storage.

Revision ID: 0003_forecast_runs
Revises: 0002_order_book_history
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_forecast_runs"
down_revision: str | None = "0002_order_book_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_runs",
        sa.Column("run_id", sa.String(length=36), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("question", sa.String(length=3000), nullable=False),
        sa.Column("market_price_yes", sa.Float(), nullable=False),
        sa.Column("probability_yes", sa.Float(), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=False),
        sa.Column("upper_bound", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("disagreement", sa.Float(), nullable=False),
        sa.Column("evidence_coverage", sa.Float(), nullable=False),
        sa.Column("resolution_clarity", sa.Float(), nullable=False),
        sa.Column("average_evidence_quality", sa.Float(), nullable=False),
        sa.Column("raw_edge", sa.Float(), nullable=False),
        sa.Column("preferred_side", sa.String(length=8), nullable=False),
        sa.Column("trade_allowed", sa.Boolean(), nullable=False),
        sa.Column("no_trade_reasons", sa.JSON(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("forecast_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_runs_market_id", "forecast_runs", ["market_id"])
    op.create_index("ix_forecast_runs_created_at", "forecast_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_forecast_runs_created_at", table_name="forecast_runs")
    op.drop_index("ix_forecast_runs_market_id", table_name="forecast_runs")
    op.drop_table("forecast_runs")
