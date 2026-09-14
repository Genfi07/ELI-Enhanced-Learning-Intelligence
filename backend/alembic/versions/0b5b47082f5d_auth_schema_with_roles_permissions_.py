"""auth schema with roles permissions sessions oauth

Revision ID: 0b5b47082f5d
Revises: c804af13f9e0
Create Date: 2026-01-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0b5b47082f5d"
down_revision: Union[str, None] = "c804af13f9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# IDs fijos para que el seed sea determinista en todos los entornos
ROLE_IDS = {
    "USER":        "11111111-1111-1111-1111-111111111101",
    "MODERATOR":   "11111111-1111-1111-1111-111111111102",
    "ADMIN":       "11111111-1111-1111-1111-111111111103",
    "SUPER_ADMIN": "11111111-1111-1111-1111-111111111104",
}

PERMISSION_IDS = {
    "users.read":   "22222222-2222-2222-2222-222222222201",
    "users.write":  "22222222-2222-2222-2222-222222222202",
    "users.delete": "22222222-2222-2222-2222-222222222203",
    "admin.panel":  "22222222-2222-2222-2222-222222222204",
    "admin.config": "22222222-2222-2222-2222-222222222205",
    "admin.audit":  "22222222-2222-2222-2222-222222222206",
    "system.logs":  "22222222-2222-2222-2222-222222222207",
}

ROLE_PERMISSIONS = {
    "USER":        [],
    "MODERATOR":   ["users.read"],
    "ADMIN":       ["users.read", "users.write", "admin.panel", "admin.config", "system.logs"],
    "SUPER_ADMIN": [
        "users.read", "users.write", "users.delete",
        "admin.panel", "admin.config", "admin.audit", "system.logs",
    ],
}


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Tablas base del sistema de autorización
    # ------------------------------------------------------------------ #
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(20), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_user_revoked", "sessions", ["user_id", "revoked_at"])

    op.create_table(
        "oauth_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    # ------------------------------------------------------------------ #
    # 2. Seed de roles y permisos
    # ------------------------------------------------------------------ #
    roles_values = ", ".join(
        f"('{rid}'::uuid, '{name}', '{name} role')"
        for name, rid in ROLE_IDS.items()
    )
    op.execute(f"INSERT INTO roles (id, name, description) VALUES {roles_values}")

    permissions_values = ", ".join(
        f"('{pid}'::uuid, '{code}', '{code}')"
        for code, pid in PERMISSION_IDS.items()
    )
    op.execute(f"INSERT INTO permissions (id, code, description) VALUES {permissions_values}")

    rp_rows = []
    for role_name, perms in ROLE_PERMISSIONS.items():
        role_id = ROLE_IDS[role_name]
        for p in perms:
            perm_id = PERMISSION_IDS[p]
            rp_rows.append(f"('{role_id}'::uuid, '{perm_id}'::uuid)")
    if rp_rows:
        op.execute(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES "
            + ", ".join(rp_rows)
        )

    # ------------------------------------------------------------------ #
    # 3. Refactor de users: role (string) → role_id (FK)
    # ------------------------------------------------------------------ #
    # 3.1 Añadir la columna role_id temporalmente nullable
    op.add_column(
        "users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_role_id", "users", "roles", ["role_id"], ["id"], ondelete="RESTRICT"
    )

    # 3.2 Migrar datos existentes: mapear string → id de rol
    op.execute("""
        UPDATE users
        SET role_id = (SELECT id FROM roles WHERE roles.name = users.role)
        WHERE role_id IS NULL
    """)

    # 3.3 Si algún usuario quedó sin rol (por un valor desconocido), se le asigna USER
    op.execute(f"""
        UPDATE users
        SET role_id = '{ROLE_IDS["USER"]}'::uuid
        WHERE role_id IS NULL
    """)

    # 3.4 Ahora sí, NOT NULL
    op.alter_column("users", "role_id", nullable=False)

    # 3.5 Eliminar la columna antigua
    op.drop_column("users", "role")

    # 3.6 Añadir last_login_at
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Revertir users
    op.drop_column("users", "last_login_at")
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="USER"),
    )
    op.execute("""
        UPDATE users
        SET role = (SELECT name FROM roles WHERE roles.id = users.role_id)
    """)
    op.drop_constraint("fk_users_role_id", "users", type_="foreignkey")
    op.drop_column("users", "role_id")

    # Revertir tablas
    op.drop_table("oauth_accounts")
    op.drop_index("ix_sessions_user_revoked", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")