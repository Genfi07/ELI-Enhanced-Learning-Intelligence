"""Trigger de búsqueda, fetch, YouTube y Trends.

Detecta cuándo el usuario necesita información externa y, si tiene
autonomía suficiente, invoca la tool adecuada antes de generar la respuesta:

  - `should_search_web(msg)`    → invoca web_search
  - `should_fetch_urls(msg)`    → invoca web_fetch sobre las URLs encontradas
  - `should_search_youtube(msg)` → invoca youtube_search
  - `should_search_trends(msg)`  → invoca google_trends

Los resultados se inyectan en el system prompt como bloques XML.

No usa LLM. Detección por regex. Si no matchea, no hay coste.
"""
from __future__ import annotations

import re
from typing import Any


# --------------------------------------------------------------------------- #
# Detección: búsqueda web
# --------------------------------------------------------------------------- #
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
    # Año actual/futuro reciente (con o sin preposición)
    r"en\s+(?:2024|2025|2026|2027)|del\s+(?:2024|2025|2026|2027)|"
    r"\b(?:2024|2025|2026|2027)\b|"
    r"este\s+a[ñn]o|"
    # Dónde está / dónde queda
    r"d[oó]nde\s+(?:est[aá]|queda|se\s+encuentra)\s+(?:el|la)\s+"
    r"(?:presidente|sede|oficina|embajada)|"
    # Datos / cifras / estadísticas actuales
    r"cu[aá]nt[oa]s?\s+(?:habitantes|personas|millones|km|kil[oó]metros|"
    r"a[ñn]os|d[ií]as|usuarios|miembros|empleados|pa[ií]ses)|"
    r"(?:datos|cifras|estad[ií]sticas|informe|reporte|ranking|"
    r"clasificaci[oó]n)\s+(?:actual|actuales|reciente|recientes|"
    r"de\s+\d{4}|oficial)|"
    # Tendencias / novedades
    r"(?:[uú]ltim[oa]s?|recientes?|actuales?)\s+"
    r"(?:datos|cifras|estad[ií]sticas|noticias|informes|estudios|"
    r"tendencias|avances|actualizaciones)|"
    # Comparaciones / recomendaciones
    r"(?:cu[aá]l\s+es\s+el\s+mejor|qu[eé]\s+es\s+mejor|"
    r"recomi[eé]ndame|recomendaciones\s+de|"
    r"comparativa\s+de|versus\b|\bvs\b)|"
    # Fuentes / según
    r"seg[uú]n\s+(?:fuentes|datos|estudios|informes|la\s+ONU|"
    r"la\s+OMS|el\s+INE|el\s+gobierno)|"
    # Fechas relativas
    r"(?:hoy|ayer|esta\s+semana|este\s+mes|este\s+a[ñn]o|"
    r"el\s+a[ñn]o\s+pasado|la\s+semana\s+pasada|el\s+mes\s+pasado)|"
    # --- Ampliaciones recientes ---
    r"recientemente|[uú]ltimamente|estos\s+d[ií]as|estas\s+semanas|"
    r"edici[oó]n\s+(?:m[aá]s\s+)?reciente|[uú]ltima\s+edici[oó]n|"
    r"(?:pas[oó]|sucedi[oó]|ocurri[oó])\s+(?:hoy|ayer|esta\s+semana|este\s+mes)|"
    r"qu[eé]\s+(?:pas[oó]|hubo)\s+con|"
    r"novedades\s+(?:sobre|de|en)|"
    r"actualizaciones?\s+(?:sobre|de|en)|"
    r"est[aá]\s+(?:en\s+)?(?:curso|vigente|activo|pasando)|"
    r"qu[eé]\s+se\s+sabe\s+(?:de|sobre)|"
    r"[uú]ltim[oa]\s+(?:edici[oó]n|versi[oó]n|ganador|premio|evento|"
    r"temporada|actualizaci[oó]n)"
    r")\b",
    re.IGNORECASE,
)


# Topics que NUNCA deben disparar búsqueda (identidad/origen de ELI).
_IDENTITY_EXCLUSIONS = re.compile(
    r"\b(eli|genfi|bencosme|polanco|tu\s+padre|tu\s+creador|"
    r"tu\s+origen|tu\s+identidad|ti\s+misma)\b",
    re.IGNORECASE,
)


def should_search_web(message: str) -> bool:
    """True si el mensaje pide información de actualidad."""
    if _IDENTITY_EXCLUSIONS.search(message):
        return False
    if extract_urls(message):
        return False
    if should_search_youtube(message) or should_search_trends(message):
        return False
    return bool(_SEARCH_MARKERS.search(message))


def extract_search_query(message: str) -> str:
    """Limpia el mensaje para usarlo como query de Tavily."""
    text = message.strip()
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
    return text[:300]


def format_search_results(
    payload: dict[str, Any] | None, error: str | None = None
) -> str:
    """Convierte el resultado de la tool web_search en un bloque de texto."""
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


# --------------------------------------------------------------------------- #
# Detección: fetch de URLs explícitas
# --------------------------------------------------------------------------- #
_URL_PATTERN = re.compile(
    r"https?://[^\s<>'\"\)\]]+",
    re.IGNORECASE,
)

MAX_URLS_PER_TURN = 2


def extract_urls(message: str) -> list[str]:
    """Extrae hasta MAX_URLS_PER_TURN URLs http(s) del mensaje."""
    found = _URL_PATTERN.findall(message)
    seen: set[str] = set()
    unique: list[str] = []
    for u in found:
        u = u.rstrip(".,;:!?)")
        if u and u not in seen:
            seen.add(u)
            unique.append(u)
        if len(unique) >= MAX_URLS_PER_TURN:
            break
    return unique


def should_fetch_urls(message: str) -> bool:
    """True si el mensaje contiene URLs http(s) explícitas."""
    return len(extract_urls(message)) > 0


def format_fetch_results(
    results: list[dict[str, Any]],
    errors: list[tuple[str, str]] | None = None,
) -> str:
    """Convierte los resultados de web_fetch en un bloque para el system prompt."""
    if not results and not errors:
        return ""

    lines = ["<fetched_urls>"]
    for r in results:
        lines.append(f"URL: {r.get('url', '')}")
        lines.append(f"Status: {r.get('status', 0)}")
        content_type = r.get("content_type", "")
        if content_type:
            lines.append(f"Content-Type: {content_type}")
        text = r.get("text", "") or ""
        snippet = text[:8000]
        if r.get("truncated"):
            snippet += "\n[…contenido truncado]"
        lines.append("Contenido:")
        lines.append(snippet)
        lines.append("")

    for url, err in errors or []:
        lines.append(f"URL: {url}")
        lines.append(f"ERROR: {err}")
        lines.append("")

    lines.append(
        "INSTRUCCIÓN: usa el contenido anterior para responder. Si el "
        "usuario pidió extraer datos específicos, hazlo en el formato que "
        "pidió. Cita la URL cuando aporte valor. No inventes información "
        "que no esté en el contenido."
    )
    lines.append("</fetched_urls>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Detección: YouTube
# --------------------------------------------------------------------------- #
_YOUTUBE_MARKERS = re.compile(
    r"\b("
    r"youtube|youtubers?|youtube\s+shorts?|"
    r"videos?\s+(?:de|sobre|en)\s+youtube|"
    r"canal\s+(?:de|en)\s+youtube|"
    r"qu[eé]\s+videos?|busca\s+videos?|encuentra\s+videos?|"
    r"[uú]ltimos?\s+videos?|videos?\s+recientes?|"
    r"tutorial(?:es)?\s+(?:de|sobre)|"
    r"entrevistas?\s+(?:de|con|a)|"
    r"stream(?:s|ing)?\s+de|directo\s+de|"
    r"podcast\s+(?:de|sobre)|"
    r"resumen\s+en\s+video|"
    r"contenido\s+de\s+(?:youtube|creadores?)"
    r")\b",
    re.IGNORECASE,
)


def should_search_youtube(message: str) -> bool:
    """True si el mensaje pide contenido específicamente de YouTube."""
    if _IDENTITY_EXCLUSIONS.search(message):
        return False
    return bool(_YOUTUBE_MARKERS.search(message))


def extract_youtube_query(message: str) -> str:
    """Limpia el mensaje para usarlo como query de YouTube."""
    text = message.strip()
    prefixes = (
        "busca videos sobre",
        "busca videos de",
        "busca videos en youtube sobre",
        "busca en youtube",
        "encuentra videos sobre",
        "encuentra videos de",
        "qué videos hay sobre",
        "qué videos hay de",
        "últimos videos de",
        "últimos videos sobre",
        "videos de youtube sobre",
    )
    lower = text.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip(" :,.¡!¿?")
            break
    return text[:200]


def _looks_like_recent_request(message: str) -> bool:
    """True si el usuario pide lo más reciente."""
    return bool(
        re.search(
            r"\b([uú]ltimos?|recientes?|hoy|ayer|esta\s+semana|"
            r"este\s+mes|lo\s+m[aá]s\s+nuevo)\b",
            message,
            re.IGNORECASE,
        )
    )


def extract_youtube_order(message: str) -> str:
    """Elige el orden de resultados según la intención."""
    if _looks_like_recent_request(message):
        return "date"
    return "relevance"


def format_youtube_results(
    payload: dict[str, Any] | None, error: str | None = None
) -> str:
    """Convierte el resultado de youtube_search en un bloque de texto."""
    if error:
        return (
            "<youtube_results>\n"
            "No pude completar la búsqueda en YouTube. Razón: "
            f"{error}\n"
            "INSTRUCCIÓN: dile al usuario que intentaste buscar videos pero "
            "no fue posible. No inventes la respuesta.\n"
            "</youtube_results>"
        )

    if not payload or not payload.get("results"):
        return (
            "<youtube_results>\n"
            "La búsqueda en YouTube no devolvió resultados.\n"
            "INSTRUCCIÓN: dile al usuario que buscaste pero no encontraste "
            "videos claros. No inventes.\n"
            "</youtube_results>"
        )

    lines = ["<youtube_results>"]
    lines.append(f"Query: {payload.get('query', '')}")
    lines.append(f"Order: {payload.get('order', 'relevance')}")
    lines.append(f"Resultados: {payload.get('count', 0)}")
    lines.append("")
    for i, r in enumerate(payload["results"], 1):
        lines.append(f"[{i}] {r.get('title', '(sin título)')}")
        lines.append(f"    Canal: {r.get('channel', '')}")
        lines.append(f"    Fecha: {r.get('published_at', '')[:10]}")
        lines.append(f"    URL: {r.get('url', '')}")
        desc = (r.get("description") or "").strip()
        if desc:
            lines.append(f"    {desc[:200]}")
        lines.append("")
    lines.append(
        "INSTRUCCIÓN: usa estos videos para responder. Menciona canal y "
        "fecha cuando aporte valor. Si el usuario quiere ver un video, "
        "compártele el URL. OJO: muchos canales de farándula usan títulos "
        "clickbait con MAYÚSCULAS y signos — no tomes el título como un "
        "hecho verificado; si el título es sensacionalista, dilo."
    )
    lines.append("</youtube_results>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Detección: Google Trends
# --------------------------------------------------------------------------- #
_TRENDS_MARKERS = re.compile(
    r"\b("
    r"trending|tendencias?|tendencia|"
    r"qu[eé]\s+est[aá]\s+(?:viral|de\s+moda|en\s+tendencia)|"
    r"qu[eé]\s+se\s+est[aá]\s+buscando|"
    r"lo\s+m[aá]s\s+(?:buscado|visto|popular|sonado)|"
    r"b[uú]squedas?\s+(?:populares?|en\s+alza|del\s+momento)|"
    r"inter[eé]s\s+(?:en|de)\s+(?:el\s+tiempo|google)|"
    r"google\s+trends|"
    r"qu[eé]\s+se\s+est[aá]\s+hablando|"
    r"temas?\s+(?:calientes?|del\s+momento|populares?)|"
    r"qu[eé]\s+es\s+lo\s+que\s+m[aá]s\s+se\s+busca"
    r")\b",
    re.IGNORECASE,
)


def should_search_trends(message: str) -> bool:
    """True si el mensaje pide info de tendencias."""
    if _IDENTITY_EXCLUSIONS.search(message):
        return False
    return bool(_TRENDS_MARKERS.search(message))


def extract_trends_keyword(message: str) -> str:
    """Limpia el mensaje para extraer la keyword de Trends."""
    text = message.strip()
    prefixes = (
        "qué está en tendencia sobre",
        "qué está en tendencia",
        "qué es tendencia sobre",
        "qué es tendencia",
        "qué está viral sobre",
        "qué está viral",
        "qué se está buscando sobre",
        "qué se está buscando",
        "tendencias sobre",
        "tendencias de",
        "trending sobre",
        "trending de",
        "qué se está hablando sobre",
        "qué se está hablando de",
        "temas calientes sobre",
        "temas calientes de",
    )
    lower = text.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip(" :,.¡!¿?")
            break
    return text[:100]


def extract_trends_timeframe(message: str) -> str:
    """Elige la ventana temporal según lo que pida el usuario."""
    lower = message.lower()
    if "5 años" in lower or "5 years" in lower:
        return "today 5-y"
    if "12 meses" in lower or "un año" in lower or "este año" in lower:
        return "today 12-m"
    if "3 meses" in lower or "trimestre" in lower:
        return "today 3-m"
    if "mes" in lower:
        return "today 1-m"
    if "24 horas" in lower or "hoy" in lower:
        return "now 1-d"
    if "semana" in lower or "7 días" in lower:
        return "now 7-d"
    return "today 3-m"


def format_trends_results(
    payload: dict[str, Any] | None, error: str | None = None
) -> str:
    """Convierte el resultado de google_trends en un bloque de texto."""
    if error:
        return (
            "<google_trends>\n"
            "No pude consultar Google Trends. Razón: "
            f"{error}\n"
            "INSTRUCCIÓN: dile al usuario que intentaste consultar tendencias "
            "pero no fue posible. No inventes.\n"
            "</google_trends>"
        )

    if not payload:
        return (
            "<google_trends>\n"
            "Google Trends no devolvió datos.\n"
            "INSTRUCCIÓN: dile al usuario que no encontraste datos de "
            "tendencias para esa keyword.\n"
            "</google_trends>"
        )

    series = payload.get("series") or []
    related = payload.get("related") or {}
    top = related.get("top") or []
    rising = related.get("rising") or []

    lines = ["<google_trends>"]
    lines.append(f"Keyword: {payload.get('keyword', '')}")
    lines.append(f"Ventana: {payload.get('timeframe', '')}")
    lines.append(f"Región: {payload.get('geo', 'worldwide')}")
    lines.append("")

    if series:
        values = [p["value"] for p in series]
        first = values[0] if values else 0
        last = values[-1] if values else 0
        peak = max(values) if values else 0
        peak_idx = values.index(peak) if values else 0
        peak_date = series[peak_idx]["date"][:10] if series else ""
        trend_dir = (
            "subiendo" if last > first * 1.1
            else "bajando" if last < first * 0.9
            else "estable"
        )
        lines.append(
            f"Serie: {len(series)} puntos | inicio={first} | último={last} | "
            f"pico={peak} ({peak_date}) | dirección={trend_dir}"
        )
    else:
        lines.append("Sin datos de serie temporal.")

    if top:
        lines.append("")
        lines.append("Búsquedas relacionadas (top):")
        for x in top[:5]:
            lines.append(f"  - {x['query']} ({x['value']})")
    if rising:
        lines.append("")
        lines.append("Búsquedas relacionadas (rising):")
        for x in rising[:5]:
            lines.append(f"  - {x['query']} (+{x['value']}%)")

    lines.append("")
    lines.append(
        "INSTRUCCIÓN: usa estos datos para responder sobre tendencias. "
        "Puedes mencionar la dirección (subiendo/bajando/estable) y el pico "
        "de interés. No inventes cifras exactas que no estén aquí."
    )
    lines.append("</google_trends>")
    return "\n".join(lines)