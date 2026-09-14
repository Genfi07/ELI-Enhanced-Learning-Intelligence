"""eli goals

Revision ID: 27636a648034
Revises: 6d963390ab60
Create Date: 2026-09-14 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "27636a648034"
down_revision: Union[str, None] = "6d963390ab60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eli_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Tipo de meta: LEARN, EXPLORE, IMPROVE, CONNECT, PROPOSE
        sa.Column("kind", sa.String(20), nullable=False),

        # Descripción de la meta en lenguaje natural
        sa.Column("content", sa.Text, nullable=False),

        # Origen: SELF (espontánea), TAUGHT (pedida por Genfi), DETECTED (patrón)
        sa.Column(
            "origin",
            sa.String(20),
            nullable=False,
            server_default="SELF",
        ),

        # Prioridad 1-5 (5 = máxima)
        sa.Column(
            "priority",
            sa.Integer,
            nullable=False,
            server_default="3",
        ),

        # Estado: ACTIVE, PAUSED, ACHIEVED, ABANDONED
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),

        # Lista de notas de progreso: [{"text": "...", "created_at": "..."}]
        sa.Column(
            "progress_notes",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),

        # Conversación donde surgió (nullable, se puede crear sin conversación)
        sa.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Qué patrón la disparó (si fue DETECTED)
        sa.Column("detected_pattern", sa.Text, nullable=True),

        # Temas relacionados: ["python", "async", "concurrencia"]
        sa.Column(
            "related_topics",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),

        # Metadata temporal
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Índices para consultas frecuentes
    op.create_index(
        "ix_eli_goals_status_priority",
        "eli_goals",
        ["status", sa.text("priority DESC")],
    )
    op.create_index(
        "ix_eli_goals_kind_status",
        "eli_goals",
        ["kind", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_eli_goals_kind_status", table_name="eli_goals")
    op.drop_index("ix_eli_goals_status_priority", table_name="eli_goals")
    op.drop_table("eli_goals")