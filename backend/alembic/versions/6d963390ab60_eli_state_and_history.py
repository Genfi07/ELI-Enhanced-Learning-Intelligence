"""eli state and history

Revision ID: 6d963390ab60
Revises: 494085e441b2
Create Date: 2026-09-14 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6d963390ab60"
down_revision: Union[str, None] = "494085e441b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# UUID fijo para la fila singleton del estado.
STATE_ID = "00000000-0000-0000-0000-000000000002"

# Estado inicial de ELI al nacer.
# Ánimo tranquilo, energía y foco al máximo, curiosidad media-alta.
INITIAL_MOOD = "tranquila"
INITIAL_ENERGY = 0.9
INITIAL_FOCUS = 1.0
INITIAL_CURIOSITY = 0.7


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Tabla `eli_state` (singleton)
    # ------------------------------------------------------------------ #
    op.create_table(
        "eli_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Estado afectivo actual
        sa.Column("mood", sa.String(20), nullable=False,
                  server_default=INITIAL_MOOD),
        sa.Column("energy", sa.Float, nullable=False,
                  server_default=str(INITIAL_ENERGY)),
        sa.Column("focus", sa.Float, nullable=False,
                  server_default=str(INITIAL_FOCUS)),
        sa.Column("curiosity", sa.Float, nullable=False,
                  server_default=str(INITIAL_CURIOSITY)),

        # Timestamps de referencia
        sa.Column("last_interaction_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("last_initiated_at", sa.DateTime(timezone=True),
                  nullable=True),

        # Contador de turnos desde la última actualización del estado.
        # Se incrementa en cada turno, se resetea cuando el StateService
        # decide actualizar. Cuando llega a N (5), dispara actualización.
        sa.Column("turns_since_update", sa.Integer, nullable=False,
                  server_default="0"),

        # Listas dinámicas
        sa.Column("pending_thoughts", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("recent_topics", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),

        # Metadata
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
    )

    # Garantizar una única fila (singleton).
    op.execute(
        "CREATE UNIQUE INDEX eli_state_singleton ON eli_state ((true))"
    )

    # Seed del estado inicial.
    op.execute(f"""
        INSERT INTO eli_state
            (id, mood, energy, focus, curiosity,
             turns_since_update, pending_thoughts, recent_topics)
        VALUES (
            '{STATE_ID}'::uuid,
            '{INITIAL_MOOD}',
            {INITIAL_ENERGY},
            {INITIAL_FOCUS},
            {INITIAL_CURIOSITY},
            0,
            '[]'::jsonb,
            '[]'::jsonb
        )
    """)

    # ------------------------------------------------------------------ #
    # 2. Tabla `eli_state_history` (auditoría de cambios)
    # ------------------------------------------------------------------ #
    op.create_table(
        "eli_state_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        sa.Column("mood", sa.String(20), nullable=False),
        sa.Column("energy", sa.Float, nullable=False),
        sa.Column("focus", sa.Float, nullable=False),
        sa.Column("curiosity", sa.Float, nullable=False),

        # Por qué cambió y qué lo disparó.
        sa.Column("trigger", sa.String(40), nullable=False),
        # "periodic" | "manual" | "initial" | "resumed"

        sa.Column("reason", sa.Text, nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("clock_timestamp()"), nullable=False),
    )
    op.create_index(
        "ix_eli_state_history_created",
        "eli_state_history",
        ["created_at"],
    )

    # Seed de la primera entrada de historial.
    op.execute(f"""
        INSERT INTO eli_state_history
            (id, mood, energy, focus, curiosity, trigger, reason)
        VALUES (
            gen_random_uuid(),
            '{INITIAL_MOOD}',
            {INITIAL_ENERGY},
            {INITIAL_FOCUS},
            {INITIAL_CURIOSITY},
            'initial',
            'Estado inicial al nacer ELI'
        )
    """)


def downgrade() -> None:
    op.drop_index("ix_eli_state_history_created",
                  table_name="eli_state_history")
    op.drop_table("eli_state_history")

    op.execute("DROP INDEX IF EXISTS eli_state_singleton")
    op.drop_table("eli_state")