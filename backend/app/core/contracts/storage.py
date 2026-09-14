"""Interfaz abstracta para almacenamiento de archivos.

Diseño:
  - Todos los métodos reciben `user_id`. La implementación debe garantizar
    el aislamiento: el archivo de un usuario nunca es accesible desde otro.
  - `path` es una clave lógica relativa (ej: "documents/uuid/original.pdf").
    La implementación decide cómo mapearla al backend real (filesystem, S3...).
  - Los métodos async permiten backends remotos (S3, GCS) sin cambiar la firma.

Contrato:
  - save: escribe el archivo y devuelve la clave lógica para futuras lecturas.
  - load: devuelve los bytes del archivo.
  - delete: elimina el archivo. Idempotente: no falla si ya no existe.
  - exists: True si el archivo existe.
"""
from __future__ import annotations

import uuid
from typing import Protocol


class StorageBackend(Protocol):
    name: str

    async def save(
        self,
        user_id: uuid.UUID,
        filename: str,
        data: bytes,
    ) -> str:
        """Guarda el archivo y devuelve la clave lógica para recuperarlo."""
        ...

    async def load(self, user_id: uuid.UUID, path: str) -> bytes:
        """Devuelve los bytes del archivo. Lanza FileNotFoundError si no existe."""
        ...

    async def delete(self, user_id: uuid.UUID, path: str) -> None:
        """Borra el archivo. No falla si ya no existe."""
        ...

    async def exists(self, user_id: uuid.UUID, path: str) -> bool:
        """True si el archivo existe para ese usuario."""
        ...