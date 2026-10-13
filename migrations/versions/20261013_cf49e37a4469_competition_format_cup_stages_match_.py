"""competition format, cup stages, match occurrence

Revision ID: cf49e37a4469
Revises: 7089a1b785d9
Create Date: 2026-10-13 11:21:19.846361

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf49e37a4469'
down_revision: Union[str, Sequence[str], None] = '7089a1b785d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# UEFA Champions League, Europa League, Conference League, Copa Libertadores, Club World Cup,
# World Cup, European Championship, Copa América.
TOURNAMENT_QIDS = ('Q18756', 'Q18760', 'Q59365764', 'Q184795', 'Q223366', 'Q19317', 'Q260858', 'Q178750')
OLD_STAGES = ('QUALIFYING', 'LEAGUE', 'GROUP', 'PLAYOFF', 'R32', 'R16', 'QF', 'SF', 'THIRD_PLACE', 'FINAL')


def upgrade() -> None:
    """Upgrade schema."""
    competition_format = sa.Enum('LEAGUE', 'CUP', 'LEAGUE_CUP', 'SUPER_CUP', 'TOURNAMENT', name='competition_format')
    competition_format.create(op.get_bind())
    # Existing rows: leagues by default, the tournaments by their Wikidata QIDs; the sync sets it from the seeds.
    op.add_column('competition', sa.Column('format', competition_format, server_default='LEAGUE', nullable=False))
    op.execute(
        "UPDATE competition SET format = 'TOURNAMENT' WHERE id IN ("
        " SELECT entity_id FROM external_ref WHERE entity_type = 'competition' AND source = 'wikidata'"
        f" AND source_id IN ({', '.join(repr(q) for q in TOURNAMENT_QIDS)}))"
    )
    op.alter_column('competition', 'format', server_default=None)

    op.execute("ALTER TYPE stage ADD VALUE IF NOT EXISTS 'PRELIMINARY' AFTER 'QUALIFYING'")
    op.execute("ALTER TYPE stage ADD VALUE IF NOT EXISTS 'ROUND' AFTER 'PRELIMINARY'")

    op.add_column('match', sa.Column('occurrence', sa.SmallInteger(), server_default=sa.text('1'), nullable=False))
    op.drop_constraint(op.f('uq_match_season_id_stage_home_team_id_away_team_id'), 'match', type_='unique')
    op.create_unique_constraint(op.f('uq_match_season_id_stage_home_team_id_away_team_id_occurrence'), 'match', ['season_id', 'stage', 'home_team_id', 'away_team_id', 'occurrence'])


def downgrade() -> None:
    """Downgrade schema.

    Deletes the further games of repeated pairings (occurrence > 1). Fails if any match still uses
    the PRELIMINARY or ROUND stage: delete the cup seasons first.
    """
    op.execute("DELETE FROM match WHERE occurrence > 1")
    op.drop_constraint(op.f('uq_match_season_id_stage_home_team_id_away_team_id_occurrence'), 'match', type_='unique')
    op.create_unique_constraint(op.f('uq_match_season_id_stage_home_team_id_away_team_id'), 'match', ['season_id', 'stage', 'home_team_id', 'away_team_id'])
    op.drop_column('match', 'occurrence')

    op.execute("ALTER TYPE stage RENAME TO stage_old")
    sa.Enum(*OLD_STAGES, name='stage').create(op.get_bind())
    op.execute("ALTER TABLE match ALTER COLUMN stage TYPE stage USING stage::text::stage")
    op.execute("DROP TYPE stage_old")

    op.drop_column('competition', 'format')
    sa.Enum(name='competition_format').drop(op.get_bind(), checkfirst=False)
