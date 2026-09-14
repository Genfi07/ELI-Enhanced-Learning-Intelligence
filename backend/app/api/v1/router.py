from fastapi import APIRouter

from app.admin.dashboard import router as admin_dashboard_router
from app.admin.login_page import router as admin_login_router
from app.api.v1.routers import (
    admin,
    auth,
    chat,
    conversations,
    files,
    health,
    memory,
    tools,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
api_router.include_router(memory.router)
api_router.include_router(files.router)
api_router.include_router(tools.router)
api_router.include_router(admin.router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_login_router)