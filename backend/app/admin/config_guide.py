"""Guía descriptiva de cada configuración dinámica de ELI.

Fuente única de verdad para:
  - Tooltip `?` al lado de cada clave en /admin/config
  - Modal "Ver guía" con explicación detallada

Cada entrada tiene:
  short:       tooltip de una línea
  description: explicación larga (1-3 frases)
  values:      valores válidos (si aplica)
  impact:      qué se rompe si se configura mal (si aplica)
  example:     ejemplo típico (si aplica)
"""
from __future__ import annotations

CONFIG_GUIDE: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    "llm_provider": {
        "short": "Proveedor LLM principal.",
        "description": "Determina a qué API se envía cada turno del chat. Los demás proveedores de la cadena solo se usan si este falla.",
        "values": "openai | groq | mistral | openrouter | gemini | ollama",
        "impact": "Un valor desconocido deja a ELI sin poder responder.",
        "example": "openai",
    },
    "llm_default_model": {
        "short": "Modelo por defecto en modo STANDARD.",
        "description": "Modelo que se usa en la mayoría de turnos. Debe existir en el proveedor principal.",
        "values": "Nombre exacto del modelo en el proveedor",
        "impact": "Si no existe, todas las respuestas fallan y caen al fallback.",
        "example": "openai/gpt-oss-120b",
    },
    "llm_deep_model": {
        "short": "Modelo para modo DEEP.",
        "description": "Modelo que se usa cuando ELI decide que la pregunta requiere más razonamiento. Suele ser más caro y lento.",
        "impact": "Igual que llm_default_model: si no existe, cae al fallback.",
        "example": "openai/gpt-oss-120b",
    },
    "llm_fallback_chain": {
        "short": "Cadena de proveedores si el principal falla.",
        "description": "Lista ordenada separada por comas. Si el proveedor principal devuelve error, se prueba el siguiente y así hasta agotar la cadena.",
        "values": "Nombres separados por comas: groq,mistral,openrouter,gemini,ollama",
        "impact": "Proveedores mal escritos se saltan silenciosamente.",
        "example": "groq,mistral,openrouter,gemini,ollama",
    },
    "llm_request_timeout_s": {
        "short": "Timeout por request al LLM (segundos).",
        "description": "Cuánto espera ELI antes de cancelar una llamada al proveedor y saltar al siguiente de la cadena.",
        "values": "Entero en segundos, recomendado 30–300",
        "impact": "Muy bajo corta respuestas largas; muy alto bloquea el chat.",
        "example": "120",
    },

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #
    "embeddings_provider": {
        "short": "Enrutado del proveedor de embeddings.",
        "description": "`chain` usa la cadena automática con fallback. Un nombre específico fuerza ese proveedor.",
        "values": "chain | gemini | mistral-embed | voyage | cohere | jina | ollama",
        "example": "chain",
    },
    "gemini_embeddings_model": {
        "short": "Modelo de embeddings de Gemini.",
        "description": "Modelo que convierte texto en vectores cuando se usa Gemini para embeddings.",
        "example": "gemini-embedding-001",
    },
    "jina_model": {
        "short": "Modelo de embeddings de Jina.",
        "description": "Modelo de Jina a usar para vectorizar texto.",
        "example": "jina-embeddings-v3",
    },
    "ollama_embeddings_model": {
        "short": "Modelo de embeddings locales en Ollama.",
        "description": "Se usa cuando la cadena cae hasta Ollama (último recurso).",
        "example": "nomic-embed-text",
    },

    # ------------------------------------------------------------------ #
    # Memoria
    # ------------------------------------------------------------------ #
    "memory_enabled": {
        "short": "Activa la memoria a largo plazo.",
        "description": "Si está activo, ELI guarda hechos sobre el usuario y los recupera en turnos posteriores.",
        "values": "true | false",
        "impact": "Desactivarlo hace que ELI olvide todo entre conversaciones.",
    },
    "memory_extraction_enabled": {
        "short": "Extrae memorias automáticamente.",
        "description": "Si está activo, ELI analiza cada turno y guarda hechos nuevos sin que el usuario lo pida.",
        "values": "true | false",
    },
    "memory_token_budget": {
        "short": "Tokens máximos para memorias en el contexto.",
        "description": "Presupuesto dedicado a inyectar memorias recuperadas en cada turno.",
        "values": "Entero en tokens (recomendado 200–2000)",
    },
    "memory_top_k": {
        "short": "Cuántas memorias se recuperan por turno.",
        "description": "Número máximo de recuerdos relevantes que se inyectan en el contexto.",
        "values": "Entero 1–20",
    },

    # ------------------------------------------------------------------ #
    # RAG
    # ------------------------------------------------------------------ #
    "rag_enabled": {
        "short": "Activa la búsqueda en documentos.",
        "description": "Si está activo, ELI busca en los documentos subidos por el usuario antes de responder.",
        "values": "true | false",
        "impact": "Desactivarlo ignora todos los archivos del usuario.",
    },
    "rag_top_k": {
        "short": "Chunks recuperados por consulta RAG.",
        "description": "Número de fragmentos relevantes que se traen de la base vectorial.",
        "values": "Entero 1–20",
    },
    "rag_token_budget": {
        "short": "Tokens máximos para RAG.",
        "description": "Presupuesto dedicado a inyectar chunks de documentos en el contexto.",
        "values": "Entero en tokens",
    },
    "rag_max_chunks_per_doc": {
        "short": "Chunks máximos por documento.",
        "description": "Al indexar un documento, cuántos fragmentos se generan como máximo. Limita el coste de embeddings.",
        "values": "Entero 50–2000",
    },

    # ------------------------------------------------------------------ #
    # Razonamiento
    # ------------------------------------------------------------------ #
    "planning_enabled": {
        "short": "Activa la planificación en modo DEEP.",
        "description": "Si está activo, ELI divide preguntas complejas en pasos antes de responder.",
        "values": "true | false",
    },
    "planning_max_steps": {
        "short": "Pasos máximos en un plan.",
        "description": "Cuántos pasos puede descomponer ELI antes de sintetizar la respuesta.",
        "values": "Entero 2–15",
    },
    "planning_step_max_tokens": {
        "short": "Tokens máximos por paso.",
        "description": "Presupuesto de tokens para cada paso de la planificación.",
        "values": "Entero en tokens",
    },
    "planning_final_context_chars": {
        "short": "Caracteres de contexto para la síntesis final.",
        "description": "Cuánto texto de los pasos previos se pasa al modelo que genera la respuesta final.",
        "values": "Entero en caracteres",
    },
    "summarization_enabled": {
        "short": "Resume conversaciones largas.",
        "description": "Si está activo, ELI comprime turnos antiguos en un resumen para ahorrar tokens.",
        "values": "true | false",
    },
    "summarization_threshold": {
        "short": "Mensajes antes de activar el resumen.",
        "description": "Al superar este número de mensajes, se resumen los más antiguos.",
        "values": "Entero 10–200",
    },
    "summarization_keep_recent": {
        "short": "Mensajes recientes que no se resumen.",
        "description": "Siempre se mantienen intactos los últimos N mensajes. Los anteriores se resumen.",
        "values": "Entero 5–100",
    },

    # ------------------------------------------------------------------ #
    # Herramientas
    # ------------------------------------------------------------------ #
    "web_fetch_timeout_s": {
        "short": "Timeout de web_fetch (segundos).",
        "description": "Cuánto espera la herramienta web_fetch antes de abortar una descarga.",
        "values": "Entero en segundos",
    },
    "web_fetch_max_bytes": {
        "short": "Bytes máximos descargados por web_fetch.",
        "description": "Límite de tamaño de una página antes de truncarla. Evita descargar binarios enormes.",
        "values": "Entero en bytes",
    },
    "tools_max_result_chars": {
        "short": "Caracteres máximos devueltos por una tool.",
        "description": "Cualquier resultado de herramienta se trunca a este tamaño antes de inyectarse en el contexto.",
        "values": "Entero en caracteres",
    },
    "max_tool_calls": {
        "short": "Herramientas máximas por turno.",
        "description": "Cuántas tool calls puede encadenar ELI en un solo turno antes de responder.",
        "values": "Entero 1–10",
    },

    # ------------------------------------------------------------------ #
    # Seguridad
    # ------------------------------------------------------------------ #
    "cookie_domain": {
        "short": "Dominio al que se envía la cookie de sesión.",
        "description": "Vacío = solo el host que emitió la cookie. `.tudominio.com` = también subdominios. No tocar en dev.",
        "values": "Vacío | .tudominio.com",
        "impact": "Mal valor = el navegador deja de enviar la cookie y cierras sesión en cada request.",
    },
    "cookie_samesite": {
        "short": "Política SameSite de la cookie.",
        "description": "`lax` permite navegación normal y bloquea POST cross-site. `strict` bloquea todo cross-site. `none` requiere HTTPS.",
        "values": "lax | strict | none",
    },
    "cookie_secure": {
        "short": "Cookie solo por HTTPS.",
        "description": "Si está activo, la cookie solo viaja por conexiones HTTPS. En dev con HTTP hay que desactivarlo.",
        "values": "true | false",
        "impact": "En dev con HTTP y `true`, no podrás iniciar sesión.",
    },
    "session_ttl_days": {
        "short": "Días de vida de una sesión.",
        "description": "Cuánto dura la sesión antes de pedir login otra vez.",
        "values": "Entero en días",
    },
    "max_context_tokens": {
        "short": "Tokens máximos de contexto.",
        "description": "Límite total de tokens (historial + memoria + RAG + planificación) antes de truncar.",
        "values": "Entero en tokens",
    },
    "max_response_tokens": {
        "short": "Tokens máximos de respuesta.",
        "description": "Tamaño máximo de la respuesta del LLM. Valores bajos truncan respuestas largas.",
        "values": "Entero en tokens",
    },
    "max_upload_size_mb": {
        "short": "Tamaño máximo de archivo subido (MB).",
        "description": "Límite por archivo en la ingesta. Aplica a documentos e imágenes.",
        "values": "Entero en MB",
    },
    "history_recent_messages": {
        "short": "Mensajes recientes sin resumir.",
        "description": "Cuántos mensajes recientes se pasan literalmente al LLM antes de aplicar el resumen.",
        "values": "Entero 5–100",
    },

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    "google_client_id": {
        "short": "Client ID OAuth de Google.",
        "description": "Identificador público de la app ante Google. Se obtiene en Google Cloud Console.",
    },
    "google_client_secret": {
        "short": "Client Secret OAuth de Google.",
        "description": "Secreto compartido con Google. No se puede modificar desde el panel.",
    },
    "google_redirect_uri": {
        "short": "URI de redirección OAuth.",
        "description": "A dónde redirige Google tras el login. Debe coincidir exactamente con lo registrado en Google Cloud.",
        "impact": "Si no coincide, Google rechaza el login con `redirect_uri_mismatch`.",
    },
    "oauth_redirect_after_login": {
        "short": "Ruta tras login OAuth.",
        "description": "A qué página va el usuario después de autenticarse correctamente.",
        "example": "/chat",
    },

    # ------------------------------------------------------------------ #
    # General / Infra
    # ------------------------------------------------------------------ #
    "env": {
        "short": "Entorno actual.",
        "description": "Afecta logging, cookies, y algunas políticas de seguridad.",
        "values": "dev | staging | prod",
    },
    "log_level": {
        "short": "Nivel mínimo de logs.",
        "description": "Solo se emiten logs de este nivel o superior.",
        "values": "DEBUG | INFO | WARNING | ERROR",
    },
    "trace_enabled": {
        "short": "Guarda trazas de peticiones.",
        "description": "Si está activo, cada petición se registra en request_traces para debugging y analytics.",
        "values": "true | false",
    },
    "ingestion_enabled": {
        "short": "Procesa archivos subidos.",
        "description": "Si está activo, los documentos subidos se extraen, dividen en chunks y se vectorizan.",
        "values": "true | false",
    },
    "storage_root": {
        "short": "Ruta raíz para archivos subidos.",
        "description": "Directorio donde se guardan documentos, imágenes y artefactos.",
    },
    "secret_key": {
        "short": "Clave para firmar sesiones.",
        "description": "Usada para firmar cookies y tokens. Cámbiala en producción por un valor aleatorio largo.",
        "impact": "Cambiarla invalida todas las sesiones activas.",
    },
    "database_url": {
        "short": "URL de conexión a Postgres.",
        "description": "Cadena de conexión asyncpg. No tocar en producción sin supervisión.",
    },

    # ------------------------------------------------------------------ #
    # API keys / endpoints de proveedores
    # ------------------------------------------------------------------ #
    "openai_api_key": {
        "short": "API key del proveedor OpenAI-compatible.",
        "description": "Con la base_url por defecto apunta a Groq. Cambia la key si cambias de proveedor.",
    },
    "openai_base_url": {
        "short": "Endpoint OpenAI-compatible.",
        "description": "URL base del proveedor que habla el protocolo OpenAI. Groq, Together, Fireworks, etc.",
    },
    "cerebras_api_key": {
        "short": "API key de Cerebras.",
        "description": "Solo se usa si configuras el proveedor Cerebras en la cadena.",
    },
    "cerebras_base_url": {
        "short": "Endpoint de Cerebras.",
        "description": "URL base de la API de Cerebras.",
    },
    "cerebras_model": {
        "short": "Modelo de Cerebras.",
        "description": "Modelo por defecto si se usa Cerebras.",
    },
    "cohere_api_key": {
        "short": "API key de Cohere.",
        "description": "Se usa para el proveedor de embeddings de Cohere.",
    },
    "gemini_api_key": {
        "short": "API key de Google Gemini.",
        "description": "Se usa para chat y embeddings de Gemini, y para Gemini Vision (OCR de imágenes).",
    },
    "gemini_base_url": {
        "short": "Endpoint OpenAI-compatible de Gemini.",
        "description": "URL base del endpoint compatible OpenAI de Google.",
    },
    "gemini_model": {
        "short": "Modelo de chat de Gemini.",
        "description": "Modelo por defecto si el proveedor activo es Gemini.",
    },
    "jina_api_key": {
        "short": "API key de Jina.",
        "description": "Se usa para el proveedor de embeddings de Jina.",
    },
    "mistral_api_key": {
        "short": "API key de Mistral.",
        "description": "Se usa para chat y embeddings de Mistral.",
    },
    "mistral_base_url": {
        "short": "Endpoint de Mistral.",
        "description": "URL base de la API de Mistral.",
    },
    "mistral_model": {
        "short": "Modelo de Mistral.",
        "description": "Modelo por defecto si el proveedor es Mistral.",
    },
    "openrouter_api_key": {
        "short": "API key de OpenRouter.",
        "description": "Se usa para el proveedor OpenRouter.",
    },
    "openrouter_base_url": {
        "short": "Endpoint de OpenRouter.",
        "description": "URL base de la API de OpenRouter.",
    },
    "openrouter_model": {
        "short": "Modelo de OpenRouter.",
        "description": "Modelo por defecto si el proveedor es OpenRouter.",
    },
    "sambanova_api_key": {
        "short": "API key de SambaNova.",
        "description": "Se usa para el proveedor SambaNova.",
    },
    "sambanova_base_url": {
        "short": "Endpoint de SambaNova.",
        "description": "URL base de la API de SambaNova.",
    },
    "sambanova_model": {
        "short": "Modelo de SambaNova.",
        "description": "Modelo por defecto si el proveedor es SambaNova.",
    },
    "ollama_base_url": {
        "short": "URL del servidor Ollama local.",
        "description": "Endpoint del Ollama local. Último recurso de la cadena si todo lo demás falla.",
    },
    "ollama_chat_model": {
        "short": "Modelo de chat en Ollama.",
        "description": "Modelo local para chat. Suele ser pequeño porque corre en CPU/GPU modestas.",
    },
    "tavily_api_key": {
        "short": "API key de Tavily.",
        "description": "Necesaria para que la herramienta de búsqueda web funcione.",
    },
    "voyage_api_key": {
        "short": "API key de Voyage.",
        "description": "Se usa para el proveedor de embeddings de Voyage.",
    },
}


def get_guide(key: str) -> dict[str, str] | None:
    """Devuelve la entrada de guía para una clave, o None si no existe."""
    return CONFIG_GUIDE.get(key)