"""tools tool_calls pending_actions and user preferences

Revision ID: 84ef795f6e4c
Revises: f4602f3c1af1
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "84ef795f6e4c"
down_revision: Union[str, None] = "f4602f3c1af1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Columna preferences en users
    # ------------------------------------------------------------------ #
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ------------------------------------------------------------------ #
    # 2. Tabla `tools`
    # ------------------------------------------------------------------ #
    op.create_table(
        "tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="builtin"),

        sa.Column(
            "parameters_schema", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "required_permissions", postgresql.JSONB, nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("min_autonomy_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("requires_confirmation", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("timeout_ms", sa.Integer, nullable=False, server_default="10000"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
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
        sa.UniqueConstraint("name", name="uq_tools_name"),
    )
    op.create_index("ix_tools_enabled_scope", "tools", ["enabled", "scope"])

    # ------------------------------------------------------------------ #
    # 3. Tabla `tool_calls`
    # ------------------------------------------------------------------ #
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "message_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column(
            "arguments", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("autonomy_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
    )
    op.create_index("ix_tool_calls_user_id", "tool_calls", ["user_id"])
    op.create_index("ix_tool_calls_conversation_id", "tool_calls", ["conversation_id"])
    op.create_index("ix_tool_calls_tool_name", "tool_calls", ["tool_name"])
    op.create_index("ix_tool_calls_status", "tool_calls", ["status"])
    op.create_index("ix_tool_calls_user_created", "tool_calls", ["user_id", "created_at"])
    op.create_index("ix_tool_calls_tool_status", "tool_calls", ["tool_name", "status"])

    # ------------------------------------------------------------------ #
    # 4. Tabla `pending_actions`
    # ------------------------------------------------------------------ #
    op.create_table(
        "pending_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "conversation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column(
            "arguments", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_pending_actions_user_id", "pending_actions", ["user_id"]
    )
    op.create_index(
        "ix_pending_actions_status", "pending_actions", ["status"]
    )
    op.create_index(
        "ix_pending_actions_user_status", "pending_actions", ["user_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_pending_actions_user_status", table_name="pending_actions")
    op.drop_index("ix_pending_actions_status", table_name="pending_actions")
    op.drop_index("ix_pending_actions_user_id", table_name="pending_actions")
    op.drop_table("pending_actions")

    op.drop_index("ix_tool_calls_tool_status", table_name="tool_calls")
    op.drop_index("ix_tool_calls_user_created", table_name="tool_calls")
    op.drop_index("ix_tool_calls_status", table_name="tool_calls")
    op.drop_index("ix_tool_calls_tool_name", table_name="tool_calls")
    op.drop_index("ix_tool_calls_conversation_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_user_id", table_name="tool_calls")
    op.drop_table("tool_calls")

    op.drop_index("ix_tools_enabled_scope", table_name="tools")
    op.drop_table("tools")

    op.drop_column("users", "preferences")