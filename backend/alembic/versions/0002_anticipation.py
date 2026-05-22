"""anticipation schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column("sessions", sa.Column("setup_doc", sa.Text, nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "anticipation_c",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "overlay_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "entities",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "session_id",
            _UUID,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("background", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "research_state",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.Column("researched_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_entities_session_slug", "entities", ["session_id", "slug"])
    op.create_unique_constraint(
        "uq_entities_session_slug", "entities", ["session_id", "slug"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_entities_session_slug", "entities", type_="unique")
    op.drop_index("ix_entities_session_slug")
    op.drop_table("entities")
    op.drop_column("sessions", "overlay_enabled")
    op.drop_column("sessions", "anticipation_c")
    op.drop_column("sessions", "setup_doc")
