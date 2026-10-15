"""fifth place stage

Revision ID: a786feda8bda
Revises: 742c9587f55b
Create Date: 2026-10-15 14:12:41.689673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a786feda8bda'
down_revision: Union[str, Sequence[str], None] = '742c9587f55b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STAGES = ('QUALIFYING', 'PRELIMINARY', 'ROUND', 'LEAGUE', 'GROUP', 'PLAYOFF', 'R32', 'R16', 'QF', 'SF', 'THIRD_PLACE', 'FINAL')


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE stage ADD VALUE IF NOT EXISTS 'FIFTH_PLACE' AFTER 'THIRD_PLACE'")


def downgrade() -> None:
    """Downgrade schema. Fails if any match still has stage FIFTH_PLACE: delete those seasons first."""
    op.execute("ALTER TYPE stage RENAME TO stage_old")
    sa.Enum(*STAGES, name="stage").create(op.get_bind())
    op.execute("ALTER TABLE match ALTER COLUMN stage TYPE stage USING stage::text::stage")
    op.execute("DROP TYPE stage_old")
