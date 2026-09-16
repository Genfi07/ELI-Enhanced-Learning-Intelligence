# Arquitectura de ELI

ELI es un monolito modular: un solo backend FastAPI, pero con módulos bien separados por responsabilidad.

## Capas

Frontend (Next.js 15) → FastAPI routers → Auth/RBAC → Orquestador → Módulos cognitivos → Providers LLM → PostgreSQL.

## Pipeline de un turno

Cuando envías un mensaje, el orquestador ejecuta:

1. load_conversation — carga historial, persiste tu mensaje.
2. check_rule_confirmation — ¿respondes a una propuesta de regla?
3. detect_rule_proposal — ¿enseñas una regla nueva?
4. detect_taught_goal — ¿pides un objetivo explícito?
5. Bloques de contexto:
   - identity (quién es ELI)
   - state (ánimo, energía, foco, curiosidad)
   - datetime (si aplica)
   - goals (metas propias)
   - attached_documents
   - web_search / web_fetch / youtube_search / google_trends
   - summary + memory
   - rag
6. Planner (solo ruta DEEP) — divide la pregunta en pasos.
7. build_context — ensambla bajo presupuesto de tokens.
8. llm_stream — streaming de la respuesta.
9. persist_assistant — guarda la respuesta.
10. Tareas de fondo: tick de estado, detección de metas, extracción de memoria.

## Sistema de tools

Cuando el orquestador quiere invocar una tool, el runtime decide:

1. ¿Existe en el registry?
2. ¿Está habilitada en BD?
3. ¿El usuario tiene autonomy_level >= min_autonomy_level de la tool?
4. ¿Tiene los permisos RBAC requeridos?
5. ¿Requiere confirmación explícita?
6. ALLOW / DENY / PENDING_CONFIRMATION.

Cada invocación (incluso DENY) genera un registro en tool_calls.

## Niveles de autonomía

- 0 — Solo conversación.
- 1 — Lectura de información.
- 2 — Herramientas internas (calculator, datetime).
- 3 — Acciones externas reversibles (web_search, web_fetch, youtube, trends).
- 4 — Acciones sensibles con confirmación.

Cap por rol (aplicado en backend): USER=2, MODERATOR=3, ADMIN=4, SUPER_ADMIN=4.

## Tools disponibles

- calculator (nivel 2) — operaciones matemáticas.
- datetime (nivel 2) — fecha/hora, diffs, sumas.
- web_search (nivel 3) — búsqueda vía Tavily.
- web_fetch (nivel 3) — descarga y limpia HTML de una URL.
- youtube_search (nivel 3) — búsqueda de videos vía YouTube Data API v3.
- google_trends (nivel 3) — interés temporal y queries relacionadas.

## Autenticación

- Login → token opaco de 32 bytes (256 bits).
- Cookie httpOnly + Secure + SameSite=Lax.
- En BD solo vive el hash SHA-256 del token.
- Cada request hashea el token entrante y busca por hash.

## Roles

- USER — chat, subir archivos, ver sus memorias.
- MODERATOR — USER + moderación (futuro).
- ADMIN — panel admin, gestionar usuarios, config con keys enmascaradas.
- SUPER_ADMIN — todo, incluye ver API keys reales y promover a otros SUPER_ADMIN.

## Permisos RBAC

- users.read / users.write / users.delete
- admin.panel — dashboard + analíticas + promover
- admin.config — leer/escribir config dinámica
- admin.audit — ver audit log

## Seguridad

- Nunca se exponen API keys a roles distintos de SUPER_ADMIN. El endpoint GET /admin/config enmascara los secretos (ej: gsk_wi...AcAl).
- Rate limit en register/login.
- Cada acción admin genera entrada en audit_logs.
- Sesiones revocables server-side.

## Observabilidad

- Logs estructurados con structlog (JSON en producción).
- Cada turno genera un registro en request_traces con timings por paso y metadatos.

## Decisiones de diseño

Monolito modular — menos complejidad operativa que microservicios, con límites claros entre módulos. Se puede extraer cualquiera en el futuro.

Async/await en todo el backend — los proveedores LLM son I/O-bound.

pgvector en vez de vector store dedicado — menos infra para nuestro volumen. Migrar a Qdrant es directo si crece.

Cookie httpOnly en vez de JWT — inmune a XSS, permite revocación server-side sin esperar expiración.