"""Create rl_allocation_log table

Revision ID: rl_allocation_log
Revises: 78a35e20b59f
Create Date: 2026-03-13 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "rl_allocation_log"
down_revision: str | Sequence[str] | None = "78a35e20b59f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create rl_allocation_log table for tracking RL allocation decisions."""
    op.create_table(
        "rl_allocation_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("disaster_id", sa.String(), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("quantity_allocated", sa.Float(), nullable=True),
        sa.Column("allocation_score", sa.Float(), nullable=True),
        sa.Column("actual_outcome", sa.String(), nullable=True),  # To be filled later
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Add index for faster queries by disaster_id
    op.create_index("ix_rl_allocation_log_disaster_id", "rl_allocation_log", ["disaster_id"])
    
    # Add index for faster queries by allocated_at
    op.create_index("ix_rl_allocation_log_allocated_at", "rl_allocation_log", ["allocated_at"])


def downgrade() -> None:
    """Drop rl_allocation_log table."""
    op.drop_index("ix_rl_allocation_log_allocated_at", table_name="rl_allocation_log")
    op.drop_index("ix_rl_allocation_log_disaster_id", table_name="rl_allocation_log")
    op.drop_table("rl_allocation_log")