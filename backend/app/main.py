from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import api_router
from app.config.settings import get_settings
from app.observability.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("eli_startup", env=settings.env, provider=settings.llm_provider)

    # Sincronizar el registry de tools con la BD. Falla silenciosa: si la BD
    # no está disponible, ELI arranca igualmente (los tests no necesitan esto).
    try:
        from app.tools.registry import build_registry
        await build_registry().sync_to_db()
    except Exception as exc:
        log.warning("tools_sync_at_startup_failed", error=str(exc))

    yield
    log.info("eli_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ELI — Enhanced Learning Intelligence",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"] if settings.env != "prod" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware de sesión requerido por Authlib: guarda el "state" del flujo
    # OAuth en `request.session` para proteger contra CSRF.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=False,  # True en prod
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "Error interno"},
        )

    app.include_router(api_router)
    return app


app = create_app()