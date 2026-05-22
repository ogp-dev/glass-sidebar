"""migration 0003 — claims.pinned + source + zone + query_echo

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-19 08:44:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add pinned column (boolean, NOT NULL, default False)
    op.add_column('claims', sa.Column('pinned', sa.Boolean(), nullable=False, server_default='false'))

    # Add source column (text, NOT NULL, default 'auto')
    op.add_column('claims', sa.Column('source', sa.Text(), nullable=False, server_default='auto'))

    # Add zone column (text, NOT NULL, default 'calm')
    op.add_column('claims', sa.Column('zone', sa.Text(), nullable=False, server_default='calm'))

    # Add query_echo column (text, nullable)
    op.add_column('claims', sa.Column('query_echo', sa.Text(), nullable=True))

    # Create check constraint for source
    op.create_check_constraint(
        'ck_claims_source',
        'claims',
        "source IN ('auto', 'manual')"
    )

    # Create check constraint for zone
    op.create_check_constraint(
        'ck_claims_zone',
        'claims',
        "zone IN ('critical', 'calm')"
    )

    # Backfill: set zone based on state (critical if state='bad', calm otherwise)
    op.execute(
        """
        UPDATE claims
        SET zone = CASE
            WHEN state = 'bad' THEN 'critical'
            ELSE 'calm'
        END
        """
    )


def downgrade() -> None:
    # Drop constraints
    op.drop_constraint('ck_claims_zone', 'claims', type_='check')
    op.drop_constraint('ck_claims_source', 'claims', type_='check')

    # Drop columns
    op.drop_column('claims', 'query_echo')
    op.drop_column('claims', 'zone')
    op.drop_column('claims', 'source')
    op.drop_column('claims', 'pinned')
