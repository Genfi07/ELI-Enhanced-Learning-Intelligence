"""Tests de los endpoints /files.

Cubren:
  - Subida de TXT válido → 202 con documento PENDING.
  - Rechazo de MIME no soportado → 415.
  - Rechazo de archivo vacío → 400.
  - Listar, obtener, borrar (soft-delete), ocultar.
  - Aislamiento entre usuarios (IDOR).
  - Reprocesar.
  - Requiere autenticación.

NOTA: la ingesta corre async en background. Estos tests NO esperan a READY;
verifican la respuesta HTTP y el estado inicial (PENDING). El test de
"end-to-end RAG" (archivo separado) comprueba la ingesta completa con datos
sembrados a mano.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


async def _register(client, name: str = "Files Tester") -> dict:
    """Registra un usuario nuevo y devuelve headers con X-Dev-User-Id."""
    email = f"files-{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "secreto123"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    client.cookies.clear()
    return {"X-Dev-User-Id": uid}


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upload_txt_success(client):
    headers = await _register(client)

    r = await client.post(
        "/api/v1/files",
        files={"file": ("nota.txt", b"Contenido del archivo de prueba.", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["title"] == "nota.txt"
    assert body["mime_type"] == "text/plain"
    assert body["status"] == "PENDING"
    assert body["scope"] == "USER"
    # Campos nuevos del ciclo de vida efímero.
    assert body["deleted_at"] is None
    assert body["hidden_at"] is None
    assert body["physical_deleted_at"] is None
    assert body["topics"] == []


@pytest.mark.asyncio
async def test_upload_unsupported_mime(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("video.mp4", b"\x00\x01\x02", "video/mp4")},
        headers=headers,
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_empty_file(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("vacio.txt", b"", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_auth(client):
    r = await client.post(
        "/api/v1/files",
        files={"file": ("x.txt", b"algo", "text/plain")},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# List / get
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_files_only_own(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"de A", "text/plain")},
        headers=headers_a,
    )
    await client.post(
        "/api/v1/files",
        files={"file": ("b.txt", b"de B", "text/plain")},
        headers=headers_b,
    )

    r = await client.get("/api/v1/files", headers=headers_a)
    assert r.status_code == 200
    titles = [d["title"] for d in r.json()]
    assert "a.txt" in titles
    assert "b.txt" not in titles


@pytest.mark.asyncio
async def test_get_file_by_id(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("mi.txt", b"contenido", "text/plain")},
        headers=headers,
    )
    doc_id = r.json()["id"]

    r = await client.get(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == doc_id


@pytest.mark.asyncio
async def test_get_file_isolated(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    r = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"de A", "text/plain")},
        headers=headers_a,
    )
    doc_id = r.json()["id"]

    r = await client.get(f"/api/v1/files/{doc_id}", headers=headers_b)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Delete (soft-delete)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_file(client):
    """DELETE hace soft-delete: la entrada sigue visible con deleted_at."""
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("borrar.txt", b"contenido", "text/plain")},
        headers=headers,
    )
    doc_id = r.json()["id"]

    # DELETE devuelve 200 con el documento actualizado (soft-delete)
    r = await client.delete(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == doc_id
    assert body["deleted_at"] is not None
    assert body["hidden_at"] is None
    assert body["chunk_count"] == 0

    # El documento SIGUE accesible por id (soft-delete)
    r = await client.get(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["deleted_at"] is not None

    # Por defecto, la lista solo muestra activos → NO debe aparecer
    r = await client.get("/api/v1/files", headers=headers)
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()]
    assert doc_id not in ids

    # Con state=deleted sí aparece
    r = await client.get("/api/v1/files?state=deleted", headers=headers)
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()]
    assert doc_id in ids

    # Con state=all también
    r = await client.get("/api/v1/files?state=all", headers=headers)
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()]
    assert doc_id in ids


@pytest.mark.asyncio
async def test_delete_twice_returns_409(client):
    """Eliminar dos veces el mismo documento devuelve 409."""
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("doble.txt", b"contenido", "text/plain")},
        headers=headers,
    )
    doc_id = r.json()["id"]

    r = await client.delete(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200

    r = await client.delete(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_delete_file_isolated(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    r = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"de A", "text/plain")},
        headers=headers_a,
    )
    doc_id = r.json()["id"]

    r = await client.delete(f"/api/v1/files/{doc_id}", headers=headers_b)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Hide
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_hide_file_after_delete(client):
    """POST /files/{id}/hide oculta la entrada permanentemente."""
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("ocultar.txt", b"contenido", "text/plain")},
        headers=headers,
    )
    doc_id = r.json()["id"]

    # No se puede ocultar sin haber eliminado antes
    r = await client.post(f"/api/v1/files/{doc_id}/hide", headers=headers)
    assert r.status_code == 409

    # Eliminar
    r = await client.delete(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200

    # Ahora sí, ocultar
    r = await client.post(f"/api/v1/files/{doc_id}/hide", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["hidden_at"] is not None

    # Ya no aparece en ninguna lista
    for state in ("active", "deleted", "all"):
        r = await client.get(f"/api/v1/files?state={state}", headers=headers)
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert doc_id not in ids

    # Pero sigue accesible por id (ELI lo sabe)
    r = await client.get(f"/api/v1/files/{doc_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["hidden_at"] is not None


@pytest.mark.asyncio
async def test_hide_file_isolated(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    r = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"de A", "text/plain")},
        headers=headers_a,
    )
    doc_id = r.json()["id"]
    await client.delete(f"/api/v1/files/{doc_id}", headers=headers_a)

    r = await client.post(f"/api/v1/files/{doc_id}/hide", headers=headers_b)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Reprocess
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_reprocess_file(client):
    headers = await _register(client)
    r = await client.post(
        "/api/v1/files",
        files={"file": ("proc.txt", b"contenido procesable", "text/plain")},
        headers=headers,
    )
    doc_id = r.json()["id"]

    r = await client.post(f"/api/v1/files/{doc_id}/reprocess", headers=headers)
    assert r.status_code == 202
    assert r.json()["id"] == doc_id
    # Estado vuelve a PENDING (reseteado por el endpoint)
    assert r.json()["status"] == "PENDING"


@pytest.mark.asyncio
async def test_reprocess_isolated(client):
    headers_a = await _register(client, "A")
    headers_b = await _register(client, "B")

    r = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"de A", "text/plain")},
        headers=headers_a,
    )
    doc_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/files/{doc_id}/reprocess", headers=headers_b
    )
    assert r.status_code == 404