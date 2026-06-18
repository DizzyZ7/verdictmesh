"""Create persistent audit and paper-trading tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("market_id", sa.String(length=128), primary_key=True),
        sa.Column("question", sa.String(length=2000), nullable=False),
        sa.Column("slug", sa.String(length=512), nullable=True),
        sa.Column("condition_id", sa.String(length=256), nullable=True),
        sa.Column("token_id_yes", sa.String(length=256), nullable=True),
        sa.Column("token_id_no", sa.String(length=256), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "market_id",
            sa.String(length=128),
            sa.ForeignKey("markets.market_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("price_yes", sa.Float(), nullable=True),
        sa.Column("price_no", sa.Float(), nullable=True),
        sa.Column("liquidity_usd", sa.Float(), nullable=False),
        sa.Column("volume_24h_usd", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("market_id", "snapshot_hash", name="uq_market_snapshot_state"),
    )
    op.create_index("ix_market_snapshots_market_id", "market_snapshots", ["market_id"])

    op.create_table(
        "trade_decisions",
        sa.Column("decision_id", sa.String(length=36), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("fair_probability_yes", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("requested_stake", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("spread", sa.Float(), nullable=False),
        sa.Column("estimated_slippage", sa.Float(), nullable=False),
        sa.Column("liquidity_usd", sa.Float(), nullable=False),
        sa.Column("resolution_risk", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.String(length=5000), nullable=False),
        sa.Column("context_bankroll", sa.Float(), nullable=False),
        sa.Column("context_exposure", sa.Float(), nullable=False),
        sa.Column("context_daily_pnl", sa.Float(), nullable=False),
        sa.Column("context_mode", sa.String(length=16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("raw_edge", sa.Float(), nullable=False),
        sa.Column("net_edge", sa.Float(), nullable=False),
        sa.Column("approved_stake", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_decisions_market_id", "trade_decisions", ["market_id"])

    op.create_table(
        "paper_orders",
        sa.Column("order_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "decision_id",
            sa.String(length=36),
            sa.ForeignKey("trade_decisions.decision_id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stake", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_orders_market_id", "paper_orders", ["market_id"])

    op.create_table(
        "paper_positions",
        sa.Column("market_id", sa.String(length=128), primary_key=True),
        sa.Column("side", sa.String(length=8), primary_key=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("average_price", sa.Float(), nullable=False),
        sa.Column("cost_basis", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "portfolio_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("starting_cash", sa.Float(), nullable=False),
        sa.Column("cash", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_state")
    op.drop_table("paper_positions")
    op.drop_index("ix_paper_orders_market_id", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_index("ix_trade_decisions_market_id", table_name="trade_decisions")
    op.drop_table("trade_decisions")
    op.drop_index("ix_market_snapshots_market_id", table_name="market_snapshots")
    op.drop_table("market_snapshots")
    op.drop_table("markets")
