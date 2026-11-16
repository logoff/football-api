"""season source: publisher, license and pages of each season's data

Revision ID: 3c1f7a9e2b40
Revises: 95be8cdfdfee
Create Date: 2026-11-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3c1f7a9e2b40'
down_revision: Union[str, Sequence[str], None] = '95be8cdfdfee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('season', sa.Column('source', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Every season so far comes from openfootball; the next sync lists the files it was read from.
    op.execute(
        """UPDATE season SET source = '{"publisher": "openfootball", "license": "CC0-1.0", "pages": []}'::jsonb"""
    )
    op.alter_column('season', 'source', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('season', 'source')
