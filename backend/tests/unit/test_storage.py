"""Tests del LocalStorageBackend.

Verifican:
  - Guardar / leer / borrar / exists.
  - Aislamiento entre usuarios (no hay forma de leer archivos ajenos).
  - Sanitización de nombres de archivo.
  - Defensa anti path traversal.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.storage.local import LocalStorageBackend, _sanitize_filename


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(root=str(tmp_path))


@pytest.fixture
def uid_a() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def uid_b() -> uuid.UUID:
    return uuid.uuid4()


# --------------------------------------------------------------------------- #
# Round trip básico
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_save_load_delete(storage, uid_a):
    data = b"contenido de prueba"
    path = await storage.save(uid_a, "mi_archivo.txt", data)
    assert path.startswith("documents/")
    assert path.endswith("mi_archivo.txt")

    assert await storage.exists(uid_a, path) is True
    assert await storage.load(uid_a, path) == data

    await storage.delete(uid_a, path)
    assert await storage.exists(uid_a, path) is False


@pytest.mark.asyncio
async def test_load_missing_raises(storage, uid_a):
    with pytest.raises(FileNotFoundError):
        await storage.load(uid_a, "documents/inexistente/foo.txt")


@pytest.mark.asyncio
async def test_delete_idempotent(storage, uid_a):
    # Borrar algo que no existe no debe lanzar
    await storage.delete(uid_a, "documents/inexistente/foo.txt")
    await storage.delete(uid_a, "documents/inexistente/foo.txt")


# --------------------------------------------------------------------------- #
# Aislamiento entre usuarios
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_users_are_isolated(storage, uid_a, uid_b):
    path_a = await storage.save(uid_a, "secreto.txt", b"de A")

    # B conoce el path (raro pero posible si lo adivina) pero no puede leerlo
    assert await storage.exists(uid_b, path_a) is False
    with pytest.raises(FileNotFoundError):
        await storage.load(uid_b, path_a)

    # A sí puede
    assert await storage.load(uid_a, path_a) == b"de A"


# --------------------------------------------------------------------------- #
# Sanitización de nombres
# --------------------------------------------------------------------------- #
def test_sanitize_filename_basic():
    assert _sanitize_filename("informe.pdf") == "informe.pdf"
    assert _sanitize_filename("mi archivo.pdf") == "mi_archivo.pdf"
    assert _sanitize_filename("archivo@raro#2024!.docx") == "archivo_raro_2024_.docx"


def test_sanitize_filename_strips_path():
    assert _sanitize_filename("../../etc/passwd") == "passwd"
    assert _sanitize_filename("/abs/path/file.txt") == "file.txt"


def test_sanitize_filename_fallback():
    assert _sanitize_filename("") == "file"
    assert _sanitize_filename("...") == "file"


def test_sanitize_filename_length_capped():
    long_name = "a" * 300 + ".pdf"
    safe = _sanitize_filename(long_name)
    assert len(safe) <= 120
    assert safe.endswith(".pdf")


# --------------------------------------------------------------------------- #
# Path traversal
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_path_traversal_is_rejected(storage, uid_a):
    # Intento de escapar del directorio del usuario
    with pytest.raises(ValueError):
        await storage.load(uid_a, "../../etc/passwd")

    # Variantes
    with pytest.raises(ValueError):
        await storage.load(uid_a, "documents/../../../etc/passwd")

    # exists no lanza, devuelve False
    assert await storage.exists(uid_a, "../../etc/passwd") is False


@pytest.mark.asyncio
async def test_save_uses_unique_directory(storage, uid_a):
    """Dos guardados con el mismo filename no colisionan."""
    p1 = await storage.save(uid_a, "informe.pdf", b"version 1")
    p2 = await storage.save(uid_a, "informe.pdf", b"version 2")
    assert p1 != p2
    assert await storage.load(uid_a, p1) == b"version 1"
    assert await storage.load(uid_a, p2) == b"version 2"