# ELI — Enhanced Learning Intelligence

Asistente conversacional con memoria persistente, RAG sobre documentos,
planificación de tareas, uso autónomo de herramientas y panel de
administración. Monolito modular en dos piezas: un backend FastAPI con
orquestación de turno y un frontend Next.js.

> Estado: **pre-beta**. Funcional end-to-end, listo para demo y uso
> interno. No listo para producción pública (falta hardening de deploy).

---

## Características principales

- **Chat con streaming** — SSE en tiempo real, cancelable.
- **Memoria a largo plazo** — ELI extrae hechos, preferencias e instrucciones
  sobre el usuario y los recupera por similitud vectorial.
- **RAG sobre documentos** — PDFs, DOCX, XLSX, TXT, MD, CSV, JSON e
  **imágenes** (OCR vía Gemini Vision).
- **Planificación (modo DEEP)** — divide preguntas complejas en pasos y los
  ejecuta antes de sintetizar la respuesta.
- **Herramientas** — `calculator`, `datetime`, `web_search` (Tavily),
  `web_fetch` (URLs), `youtube_search` (Data API v3), `google_trends`
  (pytrends). Con sistema de autonomía por nivel (0–4) y confirmación
  explícita para acciones sensibles.
- **Autonomía configurable por usuario** — capado por rol: USER=2,
  MODERATOR=3, ADMIN/SUPER_ADMIN=4.
- **Admin completo** — gestión de usuarios, roles, promoción a
  SUPER_ADMIN, config dinámica con guía, conversaciones, stats por usuario,
  audit log.
- **Ajustes del usuario** — cuenta, cambio de contraseña, conexiones
  OAuth, preferencias, exportación y eliminación de datos.
- **Seguridad** — sesiones opacas con hash SHA-256 en BD, RBAC, rate
  limit en auth, secrets enmascarados en el panel (solo SUPER_ADMIN ve
  las API keys reales).

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy async, Alembic |
| Base de datos | PostgreSQL 16 + pgvector |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind, React Query, Zustand |
| LLM | Multi-proveedor con fallback chain (Groq, Mistral, OpenRouter, Gemini, Ollama) |
| Embeddings | Multi-proveedor (Gemini, Mistral, Voyage, Cohere, Jina, Ollama) |
| Tools | Tavily (web_search), YouTube Data API v3, pytrends, httpx |
| Observabilidad | structlog + request traces en BD |

---

## Arranque rápido (Codespaces / Linux / macOS)

Requisitos previos:
- Python 3.12+
- Node.js 20+
- Docker (para Postgres)
- Ollama (opcional, para LLM local como último fallback)

### 1. Clonar y preparar entorno

```bash
git clone https://github.com/Genfi07/ELI-Enhanced-Learning-Intelligence.git
cd ELI-Enhanced-Learning-Intelligence

# Backend venv
python -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"

# Frontend
cd frontend && npm install && cd ..
```

### 2. Configurar variables de entorno

```bash
cp backend/.env.example backend/.env
# Edita backend/.env y rellena las API keys que quieras usar.
# Mínimo para arrancar: ELI_DATABASE_URL + una key de LLM.
```

### 3. Arrancar servicios base (Terminal 1)

```bash
./start.sh
```

Esto levanta:
- Postgres (Docker) en `localhost:5432`
- Ollama en `localhost:11434`
- Next.js en `localhost:3000`

### 4. Arrancar el backend (Terminal 2)

```bash
./run-backend.sh
```

Aplica migraciones pendientes y arranca Uvicorn en `localhost:8000` con
hot reload.

### 5. Abrir el chat

```
http://localhost:3000/chat
```

### Detener todo

```bash
./stop.sh
```

---

## Estructura del repositorio

```
.
├── backend/                    # FastAPI + orquestador
│   ├── app/
│   │   ├── api/                # Routers HTTP (v1)
│   │   ├── admin/              # Panel de administración
│   │   ├── auth/               # Sesiones, RBAC, OAuth Google, passwords
│   │   ├── config/             # Settings estáticos + dinámicos (BD)
│   │   ├── core/               # Orquestador, planner, context builder,
│   │   │                       # triggers de web search / YouTube / Trends
│   │   ├── db/                 # Modelos SQLAlchemy + sesión
│   │   ├── eli/                # Identidad, estado interno, metas, reglas
│   │   ├── llm/                # Providers LLM + embeddings con fallback
│   │   ├── memory/             # Extracción y recuperación de memorias
│   │   ├── rag/                # Ingesta y retrieval de documentos
│   │   ├── tools/              # Runtime + builtin tools + autonomía
│   │   └── observability/      # Logs estructurados, tracing
│   ├── alembic/                # Migraciones
│   ├── scripts/                # Utilidades CLI
│   └── tests/                  # pytest (unitarios)
├── frontend/                   # Next.js 15 (App Router)
│   ├── app/                    # Rutas (chat, admin, settings, tools, …)
│   ├── components/             # UI organizada por dominio
│   └── lib/                    # Hooks, stores, cliente API, tipos
├── infra/                      # Docker compose (Postgres)
├── docs/                       # Documentación extendida
├── start.sh                    # Arranca servicios base
├── stop.sh                     # Detiene todo
└── run-backend.sh              # Arranca Uvicorn en foreground
```

---

## Documentación

- **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — guía paso a paso
  para alguien nuevo en el proyecto.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — diseño por capas,
  pipeline de turno, sistema de tools, RBAC.
- **[docs/API.md](docs/API.md)** — referencia de endpoints HTTP.

---

## Desarrollo

### Backend

```bash
cd backend
source ../.venv/bin/activate

# Migraciones
alembic revision --autogenerate -m "descripción del cambio"
alembic upgrade head

# Tests
pytest                              # todos
pytest tests/unit -v                # unitarios con detalle
pytest -k "memory"                  # solo los que matcheen

# Lint + types
ruff check app tests
mypy app
```

### Frontend

```bash
cd frontend

npm run dev                         # hot reload
npx tsc --noEmit                    # type check
npm run lint                        # eslint
npm run build                       # producción
```

### Convenciones

- **Backend**: line-length 100 (ruff), `mypy strict`, tipos explícitos.
- **Frontend**: TypeScript estricto, componentes funcionales, React Query
  para estado servidor, Zustand para estado UI efímero.
- **Commits**: mensajes descriptivos en pasado, con secciones
  Backend / Frontend cuando aplica.

---

## Seguridad

- **Sesiones**: token opaco de 256 bits en cookie httpOnly+Secure+SameSite,
  solo el hash SHA-256 vive en BD.
- **RBAC**: permisos por endpoint (`users.read`, `admin.config`,
  `admin.panel`, …). El rol determina el conjunto.
- **Autonomía**: nivel por usuario 0–4, capado por rol en backend.
- **Secrets**: las API keys se muestran enmascaradas en `/admin/config`
  salvo para SUPER_ADMIN. El listado crudo del endpoint NUNCA devuelve
  valores completos a otros roles.
- **Rate limit**: register/login tienen límites por IP.
- **Auditoría**: cada acción administrativa genera entrada en `audit_logs`.

**Nunca** commitees tu `backend/.env`. Está en `.gitignore` y así debe
quedarse.

---

## Licencia

Proyecto privado. Todos los derechos reservados.