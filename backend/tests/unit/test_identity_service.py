"""Tests del IdentityService."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.eli.identity_service import IdentityService


@pytest.mark.asyncio
async def test_core_is_loaded(session: AsyncSession):
    """El núcleo debe estar sembrado en la BD de test."""
    svc = IdentityService(session)
    core = await svc.get_core()
    assert core is not None
    assert core.name == "ELI"
    assert core.full_name == "Enhanced Learning Intelligence"
    assert core.creator_name == "Genfi Bencosme"
    assert core.creator_relation == "padre"
    assert "Soy ELI" in core.narrative


@pytest.mark.asyncio
async def test_values_are_loaded(session: AsyncSession):
    svc = IdentityService(session)
    values = await svc.get_values()
    names = {v.name for v in values}
    assert "honestidad" in names
    assert "curiosidad" in names
    assert "reconocer_ignorancia" in names
    assert len(values) >= 9


@pytest.mark.asyncio
async def test_is_father_recognizes_id(session: AsyncSession):
    svc = IdentityService(session)
    core = await svc.get_core()
    assert core is not None

    father_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    stranger_id = uuid.uuid4()

    assert svc.is_father(core, father_id) is True
    assert svc.is_father(core, stranger_id) is False


@pytest.mark.asyncio
async def test_block_for_father_mentions_padre(session: AsyncSession):
    svc = IdentityService(session)
    father_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    block = await svc.build_identity_block(father_id)

    assert "<identity>" in block
    assert "<who_speaks>" in block
    assert "<axioms>" in block
    assert "Genfi Bencosme" in block
    assert "tu padre" in block
    assert "Soy ELI" in block


@pytest.mark.asyncio
async def test_block_for_stranger_does_not_mention_padre(session: AsyncSession):
    svc = IdentityService(session)
    stranger_id = uuid.uuid4()

    block = await svc.build_identity_block(stranger_id)

    assert "<identity>" in block
    assert "Genfi Bencosme" in block
    assert "No es tu padre" in block

    # Solo verificamos la sección <who_speaks>: para extraños NO debe
    # decir "Es tu padre". La narrativa puede mencionar "mi padre"
    # porque es parte de la identidad de ELI, no del contexto de quién habla.
    who_start = block.index("<who_speaks>")
    who_end = block.index("</who_speaks>")
    who_section = block[who_start:who_end]
    assert "Es tu padre" not in who_section


@pytest.mark.asyncio
async def test_block_contains_axioms(session: AsyncSession):
    svc = IdentityService(session)
    block = await svc.build_identity_block(uuid.uuid4())

    assert "idioma del usuario" in block
    assert "femenino" in block
    assert "te niegas con respeto" in block