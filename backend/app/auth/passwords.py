"""Hashing y verificación de contraseñas.

Usamos Argon2id, el estándar actual recomendado por OWASP. Los parámetros
están en los valores por defecto de la librería, que son seguros y actualizados.
Nunca almacenamos la contraseña en claro, y nunca hacemos comparaciones de
strings directas (todo pasa por el verificador de argon2, que es constant-time).
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_hasher = PasswordHasher()


class PasswordError(ValueError):
    """Error de validación de contraseña (formato, longitud, etc.)."""


def hash_password(plain: str) -> str:
    """Devuelve el hash Argon2id de la contraseña."""
    _validate(plain)
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica que la contraseña coincide con el hash.

    Devuelve False ante cualquier fallo, nunca lanza por contraseña incorrecta.
    """
    if not plain or not hashed:
        return False
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True si el hash debería recalcularse (porque cambió la política de hashing)."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def _validate(plain: str) -> None:
    if not isinstance(plain, str) or not plain:
        raise PasswordError("La contraseña no puede estar vacía.")
    if len(plain) < 8:
        raise PasswordError("La contraseña debe tener al menos 8 caracteres.")
    if len(plain) > 128:
        # Límite sensato: Argon2 con entradas enormes es DoS.
        raise PasswordError("La contraseña es demasiado larga (máx. 128).")