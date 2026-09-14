"""eli rule proposals

Revision ID: 667f2bab9f19
Revises: fceaa0efb079
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "667f2bab9f19"
down_revision: Union[str, None] = "fceaa0efb079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eli_rule_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="RULE"),

        sa.Column(
            "taught_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True,
        ),

        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),

        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_rule_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eli_rules.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_eli_rule_proposals_user_status",
        "eli_rule_proposals",
        ["taught_by", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_eli_rule_proposals_user_status", table_name="eli_rule_proposals"
    )
    op.drop_table("eli_rule_proposals")