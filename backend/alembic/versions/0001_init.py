"""init schema

Revision ID: 0001
Revises:
Create Date: 2026-05-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.dialects.postgresql.UUID(as_uuid=True)
_GEN_UUID = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column("clerk_user_id", sa.Text, nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "user_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "state",
            sa.Text,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("audio_source", sa.Text, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
    )

    op.create_table(
        "session_speakers",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "session_id",
            _UUID,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("source_track", sa.Text, nullable=True),
    )

    op.create_table(
        "transcript_lines",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "session_id",
            _UUID,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "speaker_id",
            _UUID,
            sa.ForeignKey("session_speakers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("start_ms", sa.Integer, nullable=False),
        sa.Column("end_ms", sa.Integer, nullable=False),
        sa.Column("is_final", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
    )
    op.create_index(
        "ix_transcript_lines_session_start",
        "transcript_lines",
        ["session_id", "start_ms"],
    )

    op.create_table(
        "claims",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "session_id",
            _UUID,
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_hash", sa.Text, nullable=False),
        sa.Column("claim_type", sa.Text, nullable=False),
        sa.Column(
            "triggered_by",
            sa.Text,
            nullable=False,
            server_default=sa.text("'reactive'"),
        ),
        sa.Column(
            "source_line_id",
            _UUID,
            sa.ForeignKey("transcript_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "state",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("verdict_text", sa.Text, nullable=True),
        sa.Column("correction_text", sa.Text, nullable=True),
        sa.Column("confidence", sa.SmallInteger, nullable=True),
        sa.Column(
            "detected_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("host_action", sa.Text, nullable=True),
        sa.Column("host_action_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_claims_session_detected", "claims", ["session_id", "detected_at"])
    op.create_index("ix_claims_hash", "claims", ["claim_hash"])
    op.create_unique_constraint(
        "uq_claims_session_claim_hash", "claims", ["session_id", "claim_hash"]
    )

    op.create_table(
        "claim_sources",
        sa.Column("id", _UUID, primary_key=True, server_default=_GEN_UUID),
        sa.Column(
            "claim_id",
            _UUID,
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("publisher", sa.Text, nullable=True),
        sa.Column("published_at", sa.Date, nullable=True),
        sa.Column("excerpt", sa.Text, nullable=True),
        sa.Column("rank", sa.SmallInteger, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("claim_sources")
    op.drop_constraint("uq_claims_session_claim_hash", "claims", type_="unique")
    op.drop_index("ix_claims_hash")
    op.drop_index("ix_claims_session_detected")
    op.drop_table("claims")
    op.drop_index("ix_transcript_lines_session_start")
    op.drop_table("transcript_lines")
    op.drop_table("session_speakers")
    op.drop_table("sessions")
    op.drop_table("users")
