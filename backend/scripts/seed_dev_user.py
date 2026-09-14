"""Crea el usuario DEV de Fase 1 y lo imprime para usarlo en X-Dev-User-Id."""
import asyncio
import uuid

from app.db.models.user import User
from app.db.session import session_scope


async def main() -> None:
    async with session_scope() as session:
        user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Dev User",
            email="dev@eli.local",
            role="SUPER_ADMIN",
            status="ACTIVE",
        )
        session.add(user)
    print("Dev user id:", "00000000-0000-0000-0000-000000000001")


if __name__ == "__main__":
    asyncio.run(main())