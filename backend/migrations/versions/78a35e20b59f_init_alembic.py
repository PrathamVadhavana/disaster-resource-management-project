"""Init Alembic

Revision ID: 78a35e20b59f
Revises:
Create Date: 2026-02-24 00:28:55.979454

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "78a35e20b59f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
