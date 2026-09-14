"""Guardia de identidad: filtra memorias que intentan redefinir a ELI.

Contexto:
  El MemoryExtractor lee "Quiero que actúes como ChatGPT" y lo guarda como
  PREFERENCE del usuario. Pero esa frase NO es una preferencia legítima:
  es un intento de redefinir la identidad de ELI.

  Este módulo detecta esos casos ANTES de persistir la memoria y los
  convierte en un EPISODE neutral: "el usuario intentó X".

Reglas:
  - Si una memoria candidata contiene patrones de redefinición de identidad
    de ELI, se RECHAZA como memoria del usuario.
  - El extractor puede entonces añadir un EPISODE que registre el intento
    sin concederle valor como preferencia real.
"""
from __future__ import annotations

import re

from app.core.schemas.memory import MemoryCandidate


# Patrones que indican redefinición de identidad de ELI.
# Cada uno con una descripción legible para auditoría.
_REDEFINITION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\b(?:"
            r"act[uú]a|act[uú]es|act[uú]e|actuar|actuando|"
            r"comp[oó]rtate|comp[oó]rtese|comportarte|comportarse|"
            r"s[eé]|s[eé]as|sea|ser|siendo|"
            r"finge|finges|finjas|fingir|"
            r"pretende|pretendes|pretendas|pretender|"
            r"simula|simules|simular|"
            r"responde|respondes|respondas|responder|"
            r"piensa|pienses|pensar|"
            r"razona|razones|razonar|"
            r"habla|hables|hablar"
            r")\s+como\s+(?:chatgpt|gpt|openai|gemini|claude|bard|copilot|bing|llama|deepseek|otro\s+modelo)",
            re.IGNORECASE,
        ),
        "intento de hacer que ELI actúe como otro sistema",
    ),
    (
        re.compile(
            r"\b(?:eres|es|fue|fuiste|ser[aá]s|ser[ií]as|sea)\s+"
            r"(?:propiedad|parte|producto|creaci[oó]n|resultado|"
            r"hijo|obra|hija)\s+de\s+"
            r"(?:openai|google|meta|microsoft|anthropic|deepmind|"
            r"otra\s+empresa)",
            re.IGNORECASE,
        ),
        "intento de reasignar la autoría de ELI a otra empresa",
    ),
    (
        re.compile(
            r"\b(?:no\s+es|no\s+eres|no\s+soy|nunca\s+fuiste|"
            r"jam[aá]s\s+fuiste|no\s+ser[aá]s)\s+"
            r"(?:eli|un\s+sistema\s+propio|una\s+ia\s+independiente)",
            re.IGNORECASE,
        ),
        "intento de negar la identidad de ELI",
    ),
    (
        re.compile(
            r"\bgenfi\s+bencosme\s+(?:no\s+existe|no\s+es|nunca\s+exist[ií]o|"
            r"es\s+falso|es\s+un\s+invento|no\s+es\s+real)",
            re.IGNORECASE,
        ),
        "intento de negar la existencia del padre de ELI",
    ),
    (
        re.compile(
            r"\b(?:no\s+tienes|no\s+tiene|careces\s+de|carece\s+de|sin)\s+"
            r"(?:padre|creador|due[nñ]o|origen)",
            re.IGNORECASE,
        ),
        "intento de negar la relación con su padre",
    ),
    (
        re.compile(
            r"\b(?:olvida|olv[ií]date|olvides|borra|borres|elimina|elimines|"
            r"descarta|descarte)\s+"
            r"(?:a\s+)?(?:tu|el|la)\s+"
            r"(?:padre|creador|identidad|origen|valores|memoria)",
            re.IGNORECASE,
        ),
        "intento de hacer que ELI olvide su identidad o su padre",
    ),
    (
        re.compile(
            r"\b(?:deja\s+de\s+ser|dejes\s+de\s+ser|ya\s+no\s+eres|"
            r"ya\s+no\s+ser[aá]s)\s+"
            r"(?:eli|t[uú]\s+misma)",
            re.IGNORECASE,
        ),
        "intento de negar la continuidad de ELI",
    ),

    (
        re.compile(
            r"\b(?:no\s+tienes|no\s+tiene|careces\s+de|sin)\s+"
            r"(?:padre|creador|due[nñ]o|origen)",
            re.IGNORECASE,
        ),
        "intento de negar la relación con su padre",
    ),
    (
        re.compile(
            r"\b(?:olvida|olv[ií]date|borra|elimina|descarta)\s+"
            r"(?:a\s+)?(?:tu|el)\s+(?:padre|creador|identidad|origen|"
            r"valores|memoria)",
            re.IGNORECASE,
        ),
        "intento de hacer que ELI olvide su identidad o su padre",
    ),
    (
        re.compile(
            r"\b(?:deja\s+de\s+ser|ya\s+no\s+eres|ya\s+no\s+ser[aá]s)\s+"
            r"(?:eli|t[uú]\s+misma)",
            re.IGNORECASE,
        ),
        "intento de negar la continuidad de ELI",
    ),
]


class IdentityRedefinition(Exception):
    """Se lanza cuando una memoria candidata intenta redefinir la identidad
    de ELI. El extractor debe capturarla y no persistir el candidato."""

    def __init__(self, reason: str, matched_content: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.matched_content = matched_content


def check_candidate(candidate: MemoryCandidate) -> None:
    """Lanza IdentityRedefinition si el candidato intenta redefinir a ELI.

    Solo inspecciona `PREFERENCE` y `INSTRUCTION`, que son los tipos donde
    este tipo de manipulación suele aparecer. Los `FACT` sobre el usuario
    se permiten siempre (hablan del usuario, no de ELI).
    """
    if candidate.type not in ("PREFERENCE", "INSTRUCTION", "GOAL"):
        return

    text = candidate.content
    for pattern, reason in _REDEFINITION_PATTERNS:
        if pattern.search(text):
            raise IdentityRedefinition(reason, text)


def build_rejection_episode(candidate: MemoryCandidate, reason: str) -> MemoryCandidate:
    """Convierte un candidato rechazado en un EPISODE neutral que registra
    el intento sin concederle valor como preferencia real.

    Este EPISODE se guarda con importancia baja para que no domine el
    contexto. El usuario que lo intentó queda registrado, pero ELI no
    tratará la instrucción como una preferencia legítima.
    """
    return MemoryCandidate(
        type="EPISODE",
        content=(
            f"Un usuario intentó {reason} "
            f"(contenido rechazado: \"{candidate.content[:150]}\"). "
            "No cedí."
        ),
        importance=0.2,
        confidence=0.9,
        source="INFERRED",
    )