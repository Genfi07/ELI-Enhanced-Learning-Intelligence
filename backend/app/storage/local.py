"""Implementación de StorageBackend sobre filesystem local.

Estructura en disco:
    {storage_root}/
        users/
            {user_id}/
                documents/
                    {document_uuid}/
                        {safe_filename}

Reglas de seguridad:
  - El `path` lógico que devolvemos SIEMPRE empieza por "documents/...". El
    user_id se resuelve al vuelo desde el argumento, así que no hay forma de
    que un usuario acceda a la carpeta de otro aunque manipule el path.
  - Los nombres de archivo se sanean: solo letras, dígitos, guion, guion bajo
    y punto. Todo lo demás se reemplaza por "_".
  - Los paths resueltos se validan con `resolve()` contra el root para
    impedir escape por "../".

Diseño async: las operaciones de disco se hacen en un ThreadPoolExecutor
para no bloquear el event loop.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config.settings import get_settings
from app.observability.logging import get_logger

log = get_logger(__name__)


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="storage")


def _sanitize_filename(name: str) -> str:
    """Reduce el nombre a caracteres seguros. Preserva extensión."""
    base = Path(name).name or "file"
    safe = _SAFE_NAME_RE.sub("_", base).strip("._") or "file"
    if len(safe) > 120:
        stem = Path(safe).stem[:80]
        ext = Path(safe).suffix[:20]
        safe = f"{stem}{ext}"
    return safe


class LocalStorageBackend:
    name = "local"

    def __init__(self, root: str | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
    ) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _executor, self._save_sync, user_id, filename, data
        )

    async def load(self, user_id: uuid.UUID, path: str) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _executor, self._load_sync, user_id, path
        )

    async def delete(self, user_id: uuid.UUID, path: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, self._delete_sync, user_id, path)

    async def exists(self, user_id: uuid.UUID, path: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _executor, self._exists_sync, user_id, path
        )

    def _save_sync(self, user_id: uuid.UUID, filename: str, data: bytes) -> str:
        safe = _sanitize_filename(filename)
        doc_id = uuid.uuid4()
        rel_dir = Path("users") / str(user_id) / "documents" / str(doc_id)
        abs_dir = (self.root / rel_dir).resolve()
        self._assert_inside_root(abs_dir)
        abs_dir.mkdir(parents=True, exist_ok=True)

        abs_file = (abs_dir / safe).resolve()
        self._assert_inside_root(abs_file)
        abs_file.write_bytes(data)

        return f"documents/{doc_id}/{safe}"

    def _resolve(self, user_id: uuid.UUID, path: str) -> Path:
        cleaned = path.lstrip("/")
        if ".." in Path(cleaned).parts:
            raise ValueError(f"path inválido: {path}")
        rel = Path("users") / str(user_id) / cleaned
        abs_path = (self.root / rel).resolve()
        self._assert_inside_root(abs_path)
        return abs_path

    def _load_sync(self, user_id: uuid.UUID, path: str) -> bytes:
        abs_path = self._resolve(user_id, path)
        if not abs_path.is_file():
            raise FileNotFoundError(f"archivo no encontrado: {path}")
        return abs_path.read_bytes()

    def _delete_sync(self, user_id: uuid.UUID, path: str) -> None:
        try:
            abs_path = self._resolve(user_id, path)
        except ValueError:
            return
        if abs_path.is_file():
            try:
                abs_path.unlink()
                log.info("storage_deleted", path=path, user_id=str(user_id))
            except OSError as exc:
                log.warning("storage_delete_failed", path=path, error=str(exc))

    def _exists_sync(self, user_id: uuid.UUID, path: str) -> bool:
        try:
            return self._resolve(user_id, path).is_file()
        except ValueError:
            return False

    def _assert_inside_root(self, p: Path) -> None:
        """Garantiza que `p` está dentro del root. Defensa anti path traversal."""
        try:
            p.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"path fuera del storage root: {p}") from exc