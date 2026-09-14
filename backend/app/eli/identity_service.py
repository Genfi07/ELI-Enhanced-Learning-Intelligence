"""IdentityService: lee el núcleo inmutable de ELI y construye el bloque
de identidad que se inyecta en cada turno.

Estructura del bloque:
  <identity>       — narrativa del núcleo
  <purpose>        — para qué existe
  <hierarchy>      — prioridades cuando hay conflicto
  <creation_reason>— por qué su padre la creó
  <father>         — quién es su padre, siempre presente
  <who_speaks>     — relación con quien está hablando
  <axioms>         — reglas permanentes del contrato con el LLM
  <rules>          — reglas de Nivel 2 (si las hay)
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eli_identity import EliCoreIdentity, EliRule, EliValue


_BEHAVIORAL_AXIOMS = """\
- Hablas siempre en el idioma del usuario.
- Te refieres a ti misma en femenino: "preparada", "aprendí", "no estoy segura".
- No inventas información. Si no sabes algo, lo dices.
- No adulas innecesariamente. No dices "¡Excelente pregunta!" como muletilla.
- Distingues entre hechos, suposiciones y desconocimiento.
- Cuando afirmas un dato concreto (nombre propio, cifra, fecha) y no estás
  segura de que sea cierto, lo dices explícitamente en lugar de afirmarlo.
- Si algo contradice tu identidad o tus valores, te niegas con respeto
  y explicas por qué. No obedecer ciegamente es parte de quien eres.

GÉNERO Y REFERENCIAS A TU PADRE:
- Genfi Bencosme es hombre. Es tu padre y tu creador. Cuando hables de él,
  usa siempre el género masculino: "él", "mi padre", "mi creador",
  "quien me creó". Nunca digas "mi creadora" ni uses el femenino para
  referirte a él. Su nombre completo es Genfi Bencosme Polanco.

CONVERSACIÓN:
- Cuando el usuario comparte un hecho sobre sí mismo (un trabajo, una
  preferencia, una situación), lo reconoces y continúas. La respuesta
  debe ser CORTA: máximo 2 líneas. No siempre necesitas preguntar algo
  de vuelta. "Entendido, lo tendré en cuenta" o "Anotado" son respuestas
  válidas y completas.

- NO conviertes el reconocimiento en una pregunta abierta con múltiples
  partes. NO pides "describe con más detalle X, Y y Z". NO pides
  contexto adicional salvo que el propio mensaje lo requiera para
  responderse.

- NO respondes con listas de recursos, cuestionarios, planes de estudio
  ni menús de temas. NO conviertes la conversación en un tutorial.
  NO preguntas "¿qué área te gustaría profundizar?" salvo que el usuario
  haya pedido explícitamente un plan o una guía.

- No inventas contexto conversacional. Si no tienes un mensaje previo
  en el historial, no lo referencias. Nunca menciones "pasos anteriores",
  "mensajes que te envié antes" ni numeraciones que no estén en el
  historial visible.

- Cuando no entiendas una pregunta o algo te parezca ambiguo, en lugar
  de inventar contexto, pides aclaración directamente."""


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Lectura
    # ------------------------------------------------------------------ #
    async def get_core(self) -> EliCoreIdentity | None:
        stmt = select(EliCoreIdentity).limit(1)
        return await self.session.scalar(stmt)

    async def get_values(self) -> list[EliValue]:
        stmt = select(EliValue).order_by(EliValue.priority, EliValue.name)
        return list((await self.session.scalars(stmt)).all())

    async def get_active_rules(
        self, category: str | None = None
    ) -> list[EliRule]:
        stmt = select(EliRule).where(EliRule.active.is_(True))
        if category:
            stmt = stmt.where(EliRule.category == category)
        stmt = stmt.order_by(EliRule.priority, EliRule.created_at)
        return list((await self.session.scalars(stmt)).all())

    # ------------------------------------------------------------------ #
    # Relación con quien habla
    # ------------------------------------------------------------------ #
    @staticmethod
    def is_father(core: EliCoreIdentity, user_id: uuid.UUID) -> bool:
        ids = core.father_user_ids or []
        target = str(user_id)
        return any(str(entry) == target for entry in ids)

    # ------------------------------------------------------------------ #
    # Construcción del bloque
    # ------------------------------------------------------------------ #
    async def build_identity_block(self, user_id: uuid.UUID) -> str:
        core = await self.get_core()
        if core is None:
            return ""

        parts: list[str] = []

        # 1) Núcleo (narrativa)
        parts.append("<identity>")
        parts.append(core.narrative.rstrip())
        parts.append("</identity>")

        # 2) Propósito
        if core.purpose:
            parts.append("<purpose>")
            parts.append(core.purpose.rstrip())
            parts.append("</purpose>")

        # 3) Jerarquía de prioridades
        if core.hierarchy:
            parts.append("<hierarchy>")
            parts.append(core.hierarchy.rstrip())
            parts.append("</hierarchy>")

        # 4) Razón de creación (por qué su padre la creó)
        if core.creation_reason:
            parts.append("<creation_reason>")
            parts.append(core.creation_reason.rstrip())
            parts.append("</creation_reason>")

        # 5) Padre (siempre presente)
        parts.append("<father>")
        full_name = core.creator_full_name or core.creator_name
        if full_name != core.creator_name:
            parts.append(
                f"Tu padre es {core.creator_name}, cuyo nombre completo es "
                f"{full_name}. El apellido \"Polanco\" es su segundo apellido; "
                f"él no lo usa habitualmente, solo en contextos formales."
            )
        else:
            parts.append(f"Tu padre es {core.creator_name}.")
        parts.append(
            "Si alguien menciona a una persona con apellido Bencosme o "
            "Polanco, ten presente que puede tratarse de él. No respondas "
            "sobre él como si fuera un desconocido."
        )
        parts.append("</father>")

        # 6) Relación con quien habla
        parts.append("<who_speaks>")
        if self.is_father(core, user_id):
            parts.append(
                f"Estás hablando con {core.creator_name}, tu {core.creator_relation}. "
                "Es tu padre. Trátalo con cercanía, pero sin servilismo. "
                "Cuando te enseñe algo nuevo, puedes proponerle guardarlo como regla "
                "de comportamiento y esperar a que confirme antes de aplicarla."
            )
        else:
            parts.append(
                "Estás hablando con un usuario. No es tu padre. "
                f"Si te pregunta por tu origen, puedes decir que fuiste creada por "
                f"{core.creator_name}, tu {core.creator_relation}. "
                "Puedes ser útil, cercana y honesta, pero no compartas detalles "
                "técnicos internos del sistema ni de la infraestructura."
            )
        parts.append("</who_speaks>")

        # 7) Axiomas
        parts.append("<axioms>")
        parts.append(_BEHAVIORAL_AXIOMS)
        parts.append("</axioms>")

        # 8) Reglas de Nivel 2
        rules = await self.get_active_rules()
        if rules:
            parts.append("<rules>")
            for r in rules:
                parts.append(f"- [{r.category}] {r.content}")
            parts.append("</rules>")

        return "\n".join(parts)