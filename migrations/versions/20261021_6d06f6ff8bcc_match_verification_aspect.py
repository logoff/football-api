"""match verification: aspect (result or events)

Revision ID: 6d06f6ff8bcc
Revises: 5c7e282a6a3c
Create Date: 2026-10-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6d06f6ff8bcc'
down_revision: Union[str, Sequence[str], None] = '5c7e282a6a3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

aspect = sa.Enum('RESULT', 'EVENTS', name='verification_aspect')


def upgrade() -> None:
    """Upgrade schema."""
    aspect.create(op.get_bind())
    # Every existing status is about the result (verify-match-events D4).
    op.add_column('match_verification', sa.Column('aspect', aspect, nullable=False, server_default='RESULT'))
    op.alter_column('match_verification', 'aspect', server_default=None)
    op.drop_constraint('uq_match_verification_match_id_reference', 'match_verification', type_='unique')
    op.create_unique_constraint(
        op.f('uq_match_verification_match_id_reference_aspect'), 'match_verification', ['match_id', 'reference', 'aspect']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM match_verification WHERE aspect = 'EVENTS'")
    op.drop_constraint(op.f('uq_match_verification_match_id_reference_aspect'), 'match_verification', type_='unique')
    op.create_unique_constraint('uq_match_verification_match_id_reference', 'match_verification', ['match_id', 'reference'])
    op.drop_column('match_verification', 'aspect')
    aspect.drop(op.get_bind())
