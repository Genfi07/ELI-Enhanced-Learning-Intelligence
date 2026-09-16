# Referencia de API

Base URL en desarrollo: http://localhost:8000/api/v1

Documentación interactiva (FastAPI auto): http://localhost:8000/docs

Autenticación: cookie de sesión httpOnly. En modo dev se puede usar el header X-Dev-User-Id: <uuid> para impersonar (solo si ELI_ENV=dev).

---

## Auth (/auth)

- POST /register — Registrar usuario nuevo.
- POST /login — Login con email + password.
- POST /logout — Cerrar sesión actual.
- GET /me — Datos del usuario autenticado.
- PATCH /me — Editar nombre y/o email.
- GET /me/preferences — Leer preferencias.
- PATCH /me/preferences — Actualizar preferencias (cap por rol).
- POST /me/change-password — Cambiar contraseña (revoca otras sesiones).
- POST /me/logout-all — Cerrar todas las sesiones.
- GET /me/export — Descargar todos mis datos (JSON).
- DELETE /me — Eliminar mi cuenta (anonimiza).
- GET /google/start — Iniciar OAuth con Google.
- GET /google/callback — Callback OAuth Google.

---

## Conversaciones (/conversations)

- GET / — Listar conversaciones del usuario.
- POST / — Crear conversación.
- GET /{id} — Obtener conversación.
- DELETE /{id} — Eliminar conversación.
- POST /{id}/messages — Enviar mensaje (streaming SSE).
- GET /{id}/messages — Listar mensajes.

---

## Memoria (/memory)

- GET / — Listar memorias activas.
- POST / — Crear memoria manualmente.
- PATCH /{id} — Editar contenido.
- DELETE /{id} — Borrar (soft delete).
- POST /{id}/restore — Restaurar memoria borrada.

---

## Documentos (/documents)

- GET / — Listar documentos.
- POST /upload — Subir archivo (multipart).
- GET /{id} — Detalles de un documento.
- DELETE /{id} — Marcar como eliminado.
- POST /{id}/hide — Ocultar de la lista.

---

## Herramientas (/tools)

- GET / — Listar tools disponibles.
- GET /calls — Historial de invocaciones.
- POST /{name}/invoke — Invocar una tool.
- GET /pending-actions — Acciones esperando confirmación.
- POST /pending-actions/{id}/confirm — Confirmar y ejecutar.
- POST /pending-actions/{id}/reject — Rechazar.

---

## Metas (/goals)

- GET / — Listar metas activas.
- POST / — Crear meta.
- PATCH /{id} — Actualizar.
- DELETE /{id} — Eliminar.

---

## Admin (/admin)

Requiere rol ADMIN o SUPER_ADMIN.

### Usuarios

- GET /users — users.read — Listar usuarios.
- GET /users/{id} — users.read — Detalle.
- POST /users — users.write — Crear usuario.
- PATCH /users/{id}/role — users.write — Cambiar rol.
- POST /users/{id}/promote — admin.panel — Promover a SUPER_ADMIN.
- POST /users/{id}/block — users.write — Bloquear.
- POST /users/{id}/unblock — users.write — Desbloquear.
- DELETE /users/{id} — users.delete — Eliminar (soft).

### Conversaciones y stats

- GET /users/{id}/conversations — admin.panel.
- GET /users/{id}/stats — users.read.
- GET /users/{id}/detail — admin.panel.
- GET /conversations — admin.panel.
- GET /conversations/{id}/messages — admin.panel.

### Configuración

- GET /config — Listar settings (secretos enmascarados si no eres SUPER_ADMIN).
- GET /config/guide — Guía descriptiva de cada clave.
- GET /config/{key} — Ver un setting.
- PUT /config/{key} — Actualizar (con audit).
- DELETE /config/{key} — Quitar override.
- POST /settings/reset-all — Borrar todos los overrides.

### Otros

- GET /audit — Audit log.
- GET /analytics/overview — Métricas globales.
- GET /analytics/timeseries?days=7 — Serie temporal.
- GET /system/health — Estado del sistema.

---

## Health

- GET /health — Healthcheck básico.
- GET /health/deep — Verifica DB + providers.

---

## Errores

Formato uniforme:

    {"detail": "Mensaje legible"}

Códigos usados:

- 400 — Datos de entrada inválidos.
- 401 — No autenticado.
- 403 — Autenticado pero sin permiso.
- 404 — Recurso no existe o no te pertenece.
- 409 — Conflicto (email duplicado, etc.).
- 429 — Rate limit alcanzado.
- 500 — Error interno (revisar logs).