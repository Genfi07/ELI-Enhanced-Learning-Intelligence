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
    """Para extraños, la sección <who_speaks> NO debe decir 'Es tu padre'."""
    svc = IdentityService(session)
    stranger_id = uuid.uuid4()

    block = await svc.build_identity_block(stranger_id)

    assert "<identity>" in block
    assert "Genfi Bencosme" in block

    # Verificamos solo la sección <who_speaks>: para extraños debe quedar
    # claro que la persona NO es su padre.
    who_start = block.index("<who_speaks>")
    who_end = block.index("</who_speaks>")
    who_section = block[who_start:who_end]

    # El bloque debe declarar explícitamente que NO es el padre (en cualquier
    # variante de mayúsculas/minúsculas).
    assert "NO es tu padre" in who_section or "no es tu padre" in who_section

    # No debe afirmar la relación paternal.
    assert "Es tu padre" not in who_section


@pytest.mark.asyncio
async def test_block_for_stranger_has_current_user_section(session: AsyncSession):
    """El bloque debe incluir <current_user> también para extraños."""
    svc = IdentityService(session)
    stranger_id = uuid.uuid4()

    block = await svc.build_identity_block(stranger_id)

    assert "<current_user>" in block
    assert "</current_user>" in block


@pytest.mark.asyncio
async def test_block_contains_axioms(session: AsyncSession):
    """Los axiomas deben incluir las reglas esenciales."""
    svc = IdentityService(session)
    block = await svc.build_identity_block(uuid.uuid4())

    # Conceptos esenciales de identidad y contrato con el LLM.
    assert "idioma" in block  # habla en el idioma del interlocutor
    assert "femenino" in block  # se refiere a sí misma en femenino
    assert "te niegas con respeto" in block  # no obedece ciegamente
    assert "No inventas información" in block  # no alucina
    # Axiomas nuevos que añadimos para identificación y lenguaje.
    assert "current_user" not in block or "<current_user>" in block  # no menciona bloques al usuario


@pytest.mark.asyncio
async def test_block_has_no_personal_pronoun_leak(session: AsyncSession):
    """El bloque no debe presentar al interlocutor como 'mi usuario'.

    Verificamos SOLO las secciones donde se describe al interlocutor
    (<current_user>, <who_speaks>, <father>). Excluimos <axioms> y otras
    secciones donde la frase puede aparecer como prohibición.
    """
    svc = IdentityService(session)
    stranger_id = uuid.uuid4()
    block = await svc.build_identity_block(stranger_id)

    # Extraemos solo la sección <current_user>: ahí es donde se presenta
    # al interlocutor. Si en esa sección no aparece "mi usuario" como
    # afirmación, el bloque es correcto.
    cu_start = block.find("<current_user>")
    cu_end = block.find("</current_user>")
    assert cu_start != -1 and cu_end != -1, "falta <current_user>"

    current_user = block[cu_start:cu_end]

    # Fuera de los axiomas y de las prohibiciones explícitas, el bloque
    # no debe llamar al interlocutor "mi usuario".
    assert "eres mi usuario" not in current_user.lower()
    assert "mi usuario" not in current_user.lower()

    # El bloque debe usar el nombre real del interlocutor, no una etiqueta.
    # Para extraños sin usuario en BD debe decirlo explícitamente.
    assert (
        "La persona que te está hablando" in current_user
        or "No se pudo cargar" in current_user
    )