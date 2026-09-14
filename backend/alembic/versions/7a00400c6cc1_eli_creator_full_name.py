"""eli creator full name

Revision ID: 7a00400c6cc1
Revises: 667f2bab9f19
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a00400c6cc1"
down_revision: Union[str, None] = "667f2bab9f19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Añadir columna (ALTER TABLE no dispara el trigger).
    op.add_column(
        "eli_core_identity",
        sa.Column("creator_full_name", sa.String(200), nullable=True),
    )

    # 2) Rellenar el campo. El UPDATE SÍ dispara el trigger, así que
    #    activamos el bypass solo durante esta operación controlada.
    op.execute("SET LOCAL eli.allow_core_update = 'true'")
    op.execute("""
        UPDATE eli_core_identity
        SET creator_full_name = 'Genfi Bencosme Polanco'
        WHERE creator_full_name IS NULL
    """)
    op.execute("SET LOCAL eli.allow_core_update = 'false'")


def downgrade() -> None:
    op.drop_column("eli_core_identity", "creator_full_name")