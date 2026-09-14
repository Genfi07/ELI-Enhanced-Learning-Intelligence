"""memory schema with pgvector

Revision ID: dfeb50dc1a32
Revises: 0b5b47082f5d
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "dfeb50dc1a32"
down_revision: Union[str, None] = "0b5b47082f5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_DIM = 1536  # text-embedding-3-small de OpenAI


def upgrade() -> None:
    # 1. Activar la extensión vectorial. Idempotente.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Tabla de memorias
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("importance", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.7"),
        sa.Column("source", sa.String(20), nullable=False, server_default="INFERRED"),
        sa.Column(
            "source_conversation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "superseded_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column(
            "meta", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # 3. Columna vectorial (aparte, porque necesita la extensión ya activa)
    op.execute(
        f"ALTER TABLE memories ADD COLUMN embedding vector({EMBEDDING_DIM})"
    )

    # 4. Índices
    op.create_index(
        "ix_memories_user_status_type",
        "memories", ["user_id", "status", "type"],
    )
    op.create_index(
        "ix_memories_user_last_used",
        "memories", ["user_id", "last_used_at"],
    )
    op.create_index(
        "ix_memories_user_id", "memories", ["user_id"],
    )

    # 5. Índice vectorial HNSW para búsqueda por similitud.
    #    vector_cosine_ops → similitud coseno (la usamos en recuperación).
    #    Parámetros por defecto razonables: m=16, ef_construction=64.
    op.execute(
        "CREATE INDEX ix_memories_embedding_hnsw ON memories "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # 6. Tabla de auditoría de cambios
    op.create_table(
        "memory_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("previous_content", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("actor", sa.String(20), nullable=False, server_default="ELI"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
    )
    op.create_index("ix_memory_events_memory_id", "memory_events", ["memory_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_events_memory_id", table_name="memory_events")
    op.drop_table("memory_events")

    op.drop_index("ix_memories_embedding_hnsw", table_name="memories")
    op.drop_index("ix_memories_user_id", table_name="memories")
    op.drop_index("ix_memories_user_last_used", table_name="memories")
    op.drop_index("ix_memories_user_status_type", table_name="memories")
    op.drop_table("memories")

    # No desactivamos la extensión vector: puede haber otras tablas usándola.