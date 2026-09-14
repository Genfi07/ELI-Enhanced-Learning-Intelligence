"""add created_at to messages

Revision ID: c804af13f9e0
Revises: 0001_initial
Create Date: 2026-09-10 19:54:33.447158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c804af13f9e0"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Añadir la columna created_at con clock_timestamp().
    #    clock_timestamp() = hora real del insert (no la de la transacción),
    #    imprescindible para ordenar mensajes insertados en la misma transacción.
    op.add_column(
        "messages",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    # 2. Reemplazar el índice antiguo (conversation_id, id) por uno que use
    #    la nueva columna de ordenación.
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "id"],
    )
    op.drop_column("messages", "created_at")