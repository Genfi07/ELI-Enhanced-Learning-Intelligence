"""documents ephemeral lifecycle

Revision ID: bb541cda279d
Revises: 27636a648034
Create Date: 2026-09-15 00:00:00

Ciclo de vida efímero de documentos:
  - El archivo físico se borra tras la ingesta (physical_deleted_at).
  - El usuario puede marcar el documento como eliminado (deleted_at).
    Esto cascadea: se borran los chunks y los embeddings.
  - El usuario puede ocultar la entrada de la lista (hidden_at).
    La entrada desaparece de UI pero ELI sigue sabiendo que existió.
  - Guardamos un summary y topics para que ELI pueda hablar del
    contenido incluso después de borrar los chunks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bb541cda279d"
down_revision: Union[str, None] = "27636a648034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "physical_deleted_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "documents",
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "topics",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Índices para filtros frecuentes.
    op.create_index(
        "ix_documents_owner_deleted",
        "documents",
        ["owner_user_id", "deleted_at"],
    )
    op.create_index(
        "ix_documents_owner_hidden",
        "documents",
        ["owner_user_id", "hidden_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_owner_hidden", table_name="documents")
    op.drop_index("ix_documents_owner_deleted", table_name="documents")
    op.drop_column("documents", "topics")
    op.drop_column("documents", "summary")
    op.drop_column("documents", "physical_deleted_at")
    op.drop_column("documents", "hidden_at")
    op.drop_column("documents", "deleted_at")