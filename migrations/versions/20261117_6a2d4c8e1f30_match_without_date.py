"""match without a date: kickoff_utc nullable, listing order puts those matches last

Revision ID: 6a2d4c8e1f30
Revises: 3c1f7a9e2b40
Create Date: 2026-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a2d4c8e1f30'
down_revision: Union[str, Sequence[str], None] = '3c1f7a9e2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match `NO_KICKOFF_SQL` in football_api.infra.models, or listings won't use the index.
SORT_KEY = "coalesce(kickoff_utc, '9999-12-31 23:59:59+00'::timestamptz)"


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('match', 'kickoff_utc', existing_type=sa.DateTime(timezone=True), nullable=True)
    op.create_index('ix_match_kickoff_sort', 'match', [sa.text(SORT_KEY), 'id'], unique=False)


def downgrade() -> None:
    """Downgrade schema. Fails while a match has no date: delete those seasons first."""
    op.drop_index('ix_match_kickoff_sort', table_name='match')
    op.alter_column('match', 'kickoff_utc', existing_type=sa.DateTime(timezone=True), nullable=False)
