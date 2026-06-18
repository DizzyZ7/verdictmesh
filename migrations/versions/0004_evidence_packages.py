"""Create evidence package storage.

Revision ID: 0004_evidence_packages
Revises: 0003_forecast_runs
Create Date: 2026-06-18
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_evidence_packages"
down_revision: str | None = "0003_forecast_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_packages",
        sa.Column("package_id", sa.String(length=36), primary_key=True),
        sa.Column("market_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("query", sa.String(length=2000), nullable=False),
        sa.Column("candidates_found", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("package_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_packages_market_id", "evidence_packages", ["market_id"])
    op.create_index("ix_evidence_packages_provider", "evidence_packages", ["provider"])
    op.create_index("ix_evidence_packages_created_at", "evidence_packages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_evidence_packages_created_at", table_name="evidence_packages")
    op.drop_index("ix_evidence_packages_provider", table_name="evidence_packages")
    op.drop_index("ix_evidence_packages_market_id", table_name="evidence_packages")
    op.drop_table("evidence_packages")
