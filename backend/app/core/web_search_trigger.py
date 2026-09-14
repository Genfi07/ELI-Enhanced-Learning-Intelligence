"""Trigger de búsqueda web.

Detecta cuándo el usuario pregunta por información de actualidad y, si
el usuario tiene autonomía suficiente, invoca la tool `web_search` antes
de generar la respuesta. El resultado se inyecta en el system prompt
como bloque <web_search_results>.

No usa LLM. Detección por regex. Si no matchea, no hay coste.
"""
from __future__ import annotations

import re
from typing import Any


# Marcadores que indican necesidad de información actual.
_SEARCH_MARKERS = re.compile(
    r"\b("
    # Posiciones actuales
    r"qui[eé]n\s+es\s+(?:el|la)\s+(?:presidente|presidenta|rey|reina|"
    r"primer\s+ministro|primer\s+ministra|alcalde|alcaldesa|"
    r"gobernador|gobernadora|papa|ceo|director|directora)|"
    r"qui[eé]n\s+(?:gan[oó]|est[aá]\s+ganando|va\s+ganando)|"
    # Eventos
    r"qu[eé]\s+pas[oó]|qu[eé]\s+est[aá]\s+pasando|qu[eé]\s+ha\s+pasado|"
    r"[uú]ltima\s+hora|[uú]ltimas\s+noticias|noticias\s+de|"
    r"actualidad|novedades\s+de|"
    # Mercados
    r"precio\s+(?:de|del|de\s+la)|cotizaci[oó]n\s+de|"
    r"cu[aá]nto\s+(?:cuesta|vale|est[aá]\s+el)|"
    # Deportes
    r"resultado\s+de|marcador\s+de|clasificaci[oó]n\s+de|"
    # Clima
    r"clima\s+en|tiempo\s+en|temperatura\s+en|"
    # Comandos explícitos
    r"busca\s+(?:en\s+internet|en\s+la\s+web|por\s+internet)|"
    r"investiga|averigua|googlea|consulta\s+en\s+internet|"
    # Año actual/futuro reciente
    r"en\s+(?:2025|2026|2027)|del\s+(?:2025|2026|2027)|"
    r"este\s+a[ñn]o|"
    # Dónde está / dónde queda algo que cambia con frecuencia
    r"d[oó]nde\s+(?:est[aá]|queda|se\s+encuentra)\s+(?:el|la)\s+"
    r"(?:presidente|sede|oficina|embajada)"
    r")\b",
    re.IGNORECASE,
)


# Topics que NUNCA deben disparar búsqueda (son identidad/origen de ELI).
_IDENTITY_EXCLUSIONS = re.compile(
    r"\b(eli|genfi|bencosme|polanco|tu\s+padre|tu\s+creador|"
    r"tu\s+origen|tu\s+identidad|ti\s+misma)\b",
    re.IGNORECASE,
)


def should_search_web(message: str) -> bool:
    """True si el mensaje pide información de actualidad."""
    if _IDENTITY_EXCLUSIONS.search(message):
        return False
    return bool(_SEARCH_MARKERS.search(message))


def extract_search_query(message: str) -> str:
    """Limpia el mensaje para usarlo como query de Tavily."""
    text = message.strip()
    # Quitar prefijos conversacionales comunes
    prefixes = (
        "busca en internet que",
        "busca en internet",
        "busca en la web que",
        "busca en la web",
        "busca por internet",
        "me puedes decir",
        "podrías buscarme",
        "puedes buscarme",
        "investiga sobre",
        "investiga",
        "averigua",
        "googlea",
        "necesito saber",
        "quiero saber",
    )
    lower = text.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip(" :,.¡!¿?")
            break
    # Limitar longitud (Tavily acepta hasta 400 chars de forma óptima)
    return text[:300]


def format_search_results(payload: dict[str, Any] | None, error: str | None = None) -> str:
    """Convierte el resultado de la tool web_search en un bloque de texto.

    Si hubo error, produce un bloque explicativo para que el LLM sepa que
    intentó buscar y no pudo.
    """
    if error:
        return (
            "<web_search_results>\n"
            "No pude completar la búsqueda web. Razón: "
            f"{error}\n"
            "INSTRUCCIÓN: dile al usuario que intentaste buscar pero no "
            "fue posible. No inventes la respuesta.\n"
            "</web_search_results>"
        )

    if not payload or not payload.get("results"):
        return (
            "<web_search_results>\n"
            "La búsqueda no devolvió resultados.\n"
            "INSTRUCCIÓN: dile al usuario que buscaste pero no encontraste "
            "información clara. No inventes la respuesta.\n"
            "</web_search_results>"
        )

    lines = ["<web_search_results>"]
    lines.append(f"Query: {payload.get('query', '')}")
    lines.append(f"Resultados: {payload.get('count', 0)}")
    lines.append("")
    answer = (payload.get("answer") or "").strip()
    if answer:
        lines.append(f"RESPUESTA SINTETIZADA: {answer}")
        lines.append("")
    for i, r in enumerate(payload["results"], 1):
        lines.append(f"[{i}] {r.get('title', '(sin título)')}")
        lines.append(f"    URL: {r.get('url', '')}")
        snippet = r.get("snippet", "").strip()
        if snippet:
            lines.append(f"    {snippet}")
        lines.append("")
    lines.append(
        "INSTRUCCIÓN: usa estos resultados para responder. Cita la fuente "
        "cuando aporte valor. Si los resultados no son concluyentes, dilo. "
        "No inventes información que no esté en los fragmentos."
    )
    lines.append("</web_search_results>")
    return "\n".join(lines)