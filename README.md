# ELI-Enhanced-Learning-Intelligence
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND (Next.js)                                         │
│  Chat · Memoria · Archivos · Perfil · Admin Dashboard       │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS / SSE (streaming)
┌───────────────────────────▼─────────────────────────────────┐
│  API GATEWAY (FastAPI routers /api/v1)                      │
│  Validación · Rate limit · Request ID · CORS · CSRF         │
└───────────────────────────┬─────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────┐
│  AUTH & AUTHORIZATION                                       │
│  Sesión · RBAC · Permisos por endpoint · Aislamiento user_id│
└───────────────────────────┬─────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────┐
│  ELI CORE — ORQUESTADOR                                     │
│  Pipeline de turno · Gestión de presupuesto · Trazas        │
│  ┌──────────────┬──────────────┬─────────────────────────┐  │
│  │ Decision     │ Context      │ Response                │  │
│  │ Engine       │ Builder      │ Validator               │  │
│  └──────────────┴──────────────┴─────────────────────────┘  │
└───┬──────────┬──────────┬──────────┬──────────┬─────────────┘
    │          │          │          │          │
┌───▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────┐
│MEMORY │ │REASON. │ │  RAG   │ │ TOOLS  │ │IDENTITY/ │
│Manager│ │Planner │ │Retriev.│ │Runtime │ │PERSONA   │
└───┬───┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬──────┘
    │         │          │          │          │
┌───▼─────────▼──────────▼──────────▼──────────▼─────────────┐
│  PROVIDER ABSTRACTION LAYER                                 │
│  LLMProvider · EmbeddingProvider · VectorStore · Storage    │
└───────────────────────────┬─────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────┐
│  PERSISTENCIA & OBSERVABILIDAD                              │
│  PostgreSQL · Redis · Object Storage · Logs · Métricas      │
└─────────────────────────────────────────────────────────────┘