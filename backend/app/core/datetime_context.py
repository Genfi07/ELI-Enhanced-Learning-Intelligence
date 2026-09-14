"""Contexto temporal inyectado en el system prompt.

Cuando el usuario pregunta por hora, fecha, día de la semana o zona
horaria, inyectamos un bloque <current_datetime> con:
  - Fecha y hora UTC actual.
  - Día de la semana.
  - Offsets comunes de zonas horarias.

El LLM con eso puede responder consultas de tiempo sin necesidad de
ejecutar una tool aparte. Casos más complejos (cálculo entre fechas,
días hasta una fecha futura) los cubrirá la tool datetime cuando se
integre en el flujo del orquestador.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone


# Marcadores que indican interés en hora/fecha actual.
_DATETIME_MARKERS = re.compile(
    r"\b("
    r"qu[eé]\s+hora|"
    r"hora\s+(?:es|son|actual|local|en|de)|"
    r"a\s+qu[eé]\s+hora|"
    r"qu[eé]\s+d[ií]a|"
    r"d[ií]a\s+de\s+(?:hoy|la\s+semana)|"
    r"qu[eé]\s+fecha|"
    r"fecha\s+(?:de\s+hoy|es|actual)|"
    r"cu[aá]ndo\s+es|"
    r"en\s+qu[eé]\s+fecha|"
    r"zona\s+horaria|"
    r"timezone|"
    r"am\s+o\s+pm|"
    r"ayer|ma[ñn]ana|pasado\s+ma[ñn]ana"
    r")\b",
    re.IGNORECASE,
)


# Zonas horarias comunes. Las mostramos al LLM para que pueda hacer el
# cálculo del offset sin tener que saberlo de memoria.
_TZ_OFFSETS = """\
Offsets comunes (aplicar según la fecha actual para verano/invierno):
- UTC: referencia (0)
- España peninsular (Europe/Madrid): UTC+2 en verano (abr-oct), UTC+1 en invierno
- República Dominicana (America/Santo_Domingo): UTC-4 todo el año
- Nueva York (America/New_York): UTC-4 en verano, UTC-5 en invierno
- Ciudad de México (America/Mexico_City): UTC-6 todo el año
- Londres (Europe/London): UTC+1 en verano, UTC+0 en invierno
- Tokio (Asia/Tokyo): UTC+9 todo el año
- Sídney (Australia/Sydney): UTC+10 en verano (oct-abr), UTC+11 en invierno
- Buenos Aires (America/Argentina/Buenos_Aires): UTC-3 todo el año
"""


def should_inject_datetime(message: str) -> bool:
    """True si el mensaje parece preguntar por hora, fecha o zona horaria."""
    return bool(_DATETIME_MARKERS.search(message))


def build_datetime_block() -> str:
    """Bloque <current_datetime> listo para inyectar en el system prompt."""
    now_utc = datetime.now(timezone.utc)
    weekday_es = {
        0: "lunes", 1: "martes", 2: "miércoles",
        3: "jueves", 4: "viernes", 5: "sábado", 6: "domingo",
    }[now_utc.weekday()]

    return (
        "<current_datetime>\n"
        f"Fecha y hora actual (UTC): "
        f"{now_utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Día de la semana: {weekday_es}\n\n"
        f"{_TZ_OFFSETS}\n"
        "INSTRUCCIÓN: si el usuario pregunta la hora sin especificar zona, "
        "responde en UTC indicándolo. Si pregunta por una ciudad o zona "
        "concreta, calcula el offset usando la tabla anterior. Nunca "
        "inventes una hora: si no puedes deducirla, dilo.\n"
        "</current_datetime>"
    )