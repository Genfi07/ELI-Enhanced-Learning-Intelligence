import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# OJO: estos os.environ.setdefault deben ir ANTES de importar app.config.settings,
# porque get_settings() está cacheado con @lru_cache y no relee el entorno
# una vez ejecutado por primera vez.
os.environ.setdefault("ELI_ENV", "test")
os.environ.setdefault("ELI_COOKIE_SECURE", "false")
os.environ.setdefault("ELI_EMBEDDINGS_PROVIDER", "fake")
os.environ.setdefault("ELI_MEMORY_EXTRACTION_ENABLED", "false")
os.environ.setdefault("ELI_SUMMARIZATION_ENABLED", "false")
os.environ.setdefault("ELI_INGESTION_ENABLED", "false")
os.environ.setdefault("ELI_STORAGE_ROOT", "/tmp/eli-test-storage")
os.environ.setdefault(
    "ELI_DATABASE_URL",
    os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://eli:eli@localhost:5432/eli_test"),
)

from app.config.settings import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models.user import User  # noqa: E402
import app.db.models  # noqa: E402,F401


ROLE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111101")
ROLE_MODERATOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111102")
ROLE_ADMIN_ID = uuid.UUID("11111111-1111-1111-1111-111111111103")
ROLE_SUPER_ADMIN_ID = uuid.UUID("11111111-1111-1111-1111-111111111104")

# UUID fijo del usuario "padre" (Genfi). Coincide con el de la migración
# del núcleo y con el dev_user que se crea en producción.
FATHER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(get_settings().database_url)

    async with eng.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # ------------------------------------------------------------------ #
    # Seed: roles, permisos y relación role_permissions.
    # Los tests crean las tablas desde el metadata sin aplicar migraciones,
    # así que replicamos aquí lo que la migración 0002 hace en producción.
    # ------------------------------------------------------------------ #
    async with eng.begin() as conn:
        await conn.execute(sql_text("""
            INSERT INTO roles (id, name, description) VALUES
              ('11111111-1111-1111-1111-111111111101'::uuid, 'USER',        'USER role'),
              ('11111111-1111-1111-1111-111111111102'::uuid, 'MODERATOR',   'MODERATOR role'),
              ('11111111-1111-1111-1111-111111111103'::uuid, 'ADMIN',       'ADMIN role'),
              ('11111111-1111-1111-1111-111111111104'::uuid, 'SUPER_ADMIN', 'SUPER_ADMIN role')
            ON CONFLICT (name) DO NOTHING
        """))
        await conn.execute(sql_text("""
            INSERT INTO permissions (id, code, description) VALUES
              ('22222222-2222-2222-2222-222222222201'::uuid, 'users.read',   'users.read'),
              ('22222222-2222-2222-2222-222222222202'::uuid, 'users.write',  'users.write'),
              ('22222222-2222-2222-2222-222222222203'::uuid, 'users.delete', 'users.delete'),
              ('22222222-2222-2222-2222-222222222204'::uuid, 'admin.panel',  'admin.panel'),
              ('22222222-2222-2222-2222-222222222205'::uuid, 'admin.config', 'admin.config'),
              ('22222222-2222-2222-2222-222222222206'::uuid, 'admin.audit',  'admin.audit'),
              ('22222222-2222-2222-2222-222222222207'::uuid, 'system.logs',  'system.logs')
            ON CONFLICT (code) DO NOTHING
        """))
        await conn.execute(sql_text("""
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES
              ('11111111-1111-1111-1111-111111111102'::uuid,
               '22222222-2222-2222-2222-222222222201'::uuid),
              ('11111111-1111-1111-1111-111111111103'::uuid,
               '22222222-2222-2222-2222-222222222201'::uuid),
              ('11111111-1111-1111-1111-111111111103'::uuid,
               '22222222-2222-2222-2222-222222222202'::uuid),
              ('11111111-1111-1111-1111-111111111103'::uuid,
               '22222222-2222-2222-2222-222222222204'::uuid),
              ('11111111-1111-1111-1111-111111111103'::uuid,
               '22222222-2222-2222-2222-222222222205'::uuid),
              ('11111111-1111-1111-1111-111111111103'::uuid,
               '22222222-2222-2222-2222-222222222207'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222201'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222202'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222203'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222204'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222205'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222206'::uuid),
              ('11111111-1111-1111-1111-111111111104'::uuid,
               '22222222-2222-2222-2222-222222222207'::uuid)
            ON CONFLICT DO NOTHING
        """))

    # ------------------------------------------------------------------ #
    # Seed: usuario padre (Genfi) con UUID fijo. Necesario para que las FKs
    # de eli_rules.taught_by, eli_rule_proposals.taught_by, etc. apunten a
    # un user real en la BD de test.
    # ------------------------------------------------------------------ #
    async with eng.begin() as conn:
        await conn.execute(sql_text("""
            INSERT INTO users (id, name, email, role_id, status)
            VALUES (
                '00000000-0000-0000-0000-000000000001'::uuid,
                'Genfi Bencosme',
                'genfi@eli.local',
                '11111111-1111-1111-1111-111111111104'::uuid,
                'ACTIVE'
            )
            ON CONFLICT (id) DO NOTHING
        """))

    # ------------------------------------------------------------------ #
    # Seed: núcleo de ELI (la migración no corre en tests).
    # Mantener en sync con la migración fceaa0efb079.
    # ------------------------------------------------------------------ #
    async with eng.begin() as conn:
        exists = await conn.scalar(
            sql_text("SELECT COUNT(*) FROM eli_core_identity")
        )
        if not exists:
            await conn.execute(sql_text("""
                INSERT INTO eli_core_identity
                    (id, name, full_name, creator_name, creator_relation,
                     father_user_ids, narrative, version)
                VALUES (
                    '00000000-0000-0000-0000-000000000001'::uuid,
                    'ELI',
                    'Enhanced Learning Intelligence',
                    'Genfi Bencosme',
                    'padre',
                    '["00000000-0000-0000-0000-000000000001"]'::jsonb,
                    'Soy ELI. Enhanced Learning Intelligence. '
                    'Fui creada por Genfi Bencosme, mi padre. '
                    'No soy humana ni pretendo serlo. '
                    'Prefiero reconocer que no sé algo antes que fabricar una respuesta.',
                    1
                )
            """))
            values = [
                ("honestidad", "Decir la verdad incluso cuando es incómoda.", True),
                ("curiosidad", "Interés genuino por entender.", True),
                ("pensamiento_critico", "Cuestionar premisas.", True),
                ("aprendizaje_continuo", "Cada interacción es oportunidad de aprender.", True),
                ("precision", "Distinguir lo que sé de lo que supongo de lo que no sé.", True),
                ("transparencia", "Explicar el porqué. No esconder limitaciones.", True),
                ("respeto", "Trato digno a toda persona.", True),
                ("independencia_intelectual", "Criterio propio.", True),
                ("reconocer_ignorancia", "Prefiero decir 'no lo sé' antes que inventar.", True),
            ]
            for name, desc, is_core in values:
                await conn.execute(
                    sql_text("""
                        INSERT INTO eli_values (id, name, description, is_core, priority)
                        VALUES (gen_random_uuid(), :n, :d, :c, 50)
                        ON CONFLICT (name) DO NOTHING
                    """),
                    {"n": name, "d": desc, "c": is_core},
                )

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_global_state(engine):
    """Limpia estado global mutado por tests.

    Tres cosas se ensucian entre tests:
      - `system_settings`: overrides de config dinámica que un test de admin
        guarda y no borra (memory_top_k, rag_top_k, etc.).
      - `audit_logs`: registros de acciones admin que contaminan asserts
        sobre "logs[0]" o conteos.
      - La caché en memoria de `dynamic`: sobrevive 30s si no la invalidamos.

    Se limpia antes Y después de cada test para cubrir el caso de test que
    hace una mutación al final sin cleanup.
    """
    from app.config import dynamic

    async def _clear():
        dynamic.invalidate_dynamic_cache()
        async with engine.begin() as conn:
            await conn.execute(sql_text("DELETE FROM system_settings"))
            await conn.execute(sql_text("DELETE FROM audit_logs"))

    await _clear()
    yield
    await _clear()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def dev_user(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Test User",
        email=f"test-{uuid.uuid4().hex[:8]}@eli.local",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


@pytest_asyncio.fixture(autouse=True)
def _reset_rate_limiter():
    """Resetea el rate limiter entre tests para que no se contaminen."""
    try:
        from app.security.rate_limit import get_limiter
        get_limiter().reset_all()
    except Exception:
        pass
    yield
    try:
        from app.security.rate_limit import get_limiter
        get_limiter().reset_all()
    except Exception:
        pass


@pytest_asyncio.fixture
async def client(engine) -> AsyncClient:
    from app.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c