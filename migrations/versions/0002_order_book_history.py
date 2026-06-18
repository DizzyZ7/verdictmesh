"""Create historical orderbook snapshot storage.

Revision ID: 0002_order_book_history
Revises: 0001_initial
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_order_book_history"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_book_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("app_market_id", sa.String(length=128), nullable=True),
        sa.Column("condition_id", sa.String(length=256), nullable=False),
        sa.Column("asset_id", sa.String(length=256), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=True),
        sa.Column("source_timestamp", sa.String(length=64), nullable=True),
        sa.Column("book_hash", sa.String(length=128), nullable=False),
        sa.Column("best_bid", sa.Float(), nullable=True),
        sa.Column("best_ask", sa.Float(), nullable=True),
        sa.Column("midpoint", sa.Float(), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("bid_notional", sa.Float(), nullable=False),
        sa.Column("ask_notional", sa.Float(), nullable=False),
        sa.Column("min_order_size", sa.Float(), nullable=True),
        sa.Column("tick_size", sa.Float(), nullable=True),
        sa.Column("neg_risk", sa.Boolean(), nullable=False),
        sa.Column("bids", sa.JSON(), nullable=False),
        sa.Column("asks", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "book_hash", name="uq_order_book_asset_hash"),
    )
    op.create_index(
        "ix_order_book_snapshots_app_market_id",
        "order_book_snapshots",
        ["app_market_id"],
    )
    op.create_index(
        "ix_order_book_snapshots_condition_id",
        "order_book_snapshots",
        ["condition_id"],
    )
    op.create_index(
        "ix_order_book_snapshots_asset_id",
        "order_book_snapshots",
        ["asset_id"],
    )
    op.create_index(
        "ix_order_book_snapshots_fetched_at",
        "order_book_snapshots",
        ["fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_order_book_snapshots_fetched_at", table_name="order_book_snapshots")
    op.drop_index("ix_order_book_snapshots_asset_id", table_name="order_book_snapshots")
    op.drop_index("ix_order_book_snapshots_condition_id", table_name="order_book_snapshots")
    op.drop_index("ix_order_book_snapshots_app_market_id", table_name="order_book_snapshots")
    op.drop_table("order_book_snapshots")
