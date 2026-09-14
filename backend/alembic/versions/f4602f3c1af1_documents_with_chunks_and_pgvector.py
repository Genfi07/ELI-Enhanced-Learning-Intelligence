"""documents with chunks and pgvector

Revision ID: f4602f3c1af1
Revises: dfeb50dc1a32
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f4602f3c1af1"
down_revision: Union[str, None] = "dfeb50dc1a32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_DIM = 1536  # text-embedding-3-small de OpenAI


def upgrade() -> None:
    # La extensión vector ya está activa desde la migración de memoria, pero
    # la reafirmamos (idempotente) para no asumir orden entre migraciones.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------ #
    # 1. Tabla `documents`
    # ------------------------------------------------------------------ #
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="USER"),

        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False, server_default="UPLOAD"),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(500), nullable=False),

        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),

        sa.Column(
            "meta", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
    )
    op.create_index("ix_documents_owner_user_id", "documents", ["owner_user_id"])
    op.create_index("ix_documents_org_id", "documents", ["org_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index(
        "ix_documents_owner_status", "documents", ["owner_user_id", "status"]
    )
    op.create_index(
        "ix_documents_owner_scope", "documents", ["owner_user_id", "scope"]
    )

    # ------------------------------------------------------------------ #
    # 2. Tabla `document_chunks`
    # ------------------------------------------------------------------ #
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "meta", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index(
        "ix_document_chunks_doc_index", "document_chunks",
        ["document_id", "chunk_index"],
    )

    # Columna vectorial (después de crear la tabla)
    op.execute(
        f"ALTER TABLE document_chunks ADD COLUMN embedding vector({EMBEDDING_DIM})"
    )

    # Índice HNSW para búsqueda por similitud coseno.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # Índice GIN para full-text search sobre el contenido.
    # Usamos 'spanish' como idioma por defecto. Configurable en el futuro.
    op.execute(
        "CREATE INDEX ix_document_chunks_content_tsv ON document_chunks "
        "USING gin (to_tsvector('spanish', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_index("ix_document_chunks_doc_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_owner_scope", table_name="documents")
    op.drop_index("ix_documents_owner_status", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_org_id", table_name="documents")
    op.drop_index("ix_documents_owner_user_id", table_name="documents")
    op.drop_table("documents")