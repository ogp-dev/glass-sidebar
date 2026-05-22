"""migration 0004 — speaker attribution on transcript_lines + claims

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21 00:00:00.000000

Adds a plain TEXT `speaker` column ("You" / "Guest") so each transcript line
and each fact-check claim records who said it. The host mic is "You", the
guest's system audio is "Guest". NULL for legacy rows, manual (Ask Glass)
cards, and anticipatory heads-up cards.

(transcript_lines already has an unused speaker_id FK to session_speakers —
Plan-A scaffolding that was never wired up. For a stable binary host/guest
distinction a plain text column is far simpler than label↔FK round-tripping.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transcript_lines', sa.Column('speaker', sa.Text(), nullable=True)
    )
    op.add_column('claims', sa.Column('speaker', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('claims', 'speaker')
    op.drop_column('transcript_lines', 'speaker')
