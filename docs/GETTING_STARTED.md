# Guía de inicio

Esta guía asume que nunca has visto el proyecto. Al terminarla tendrás ELI corriendo en tu máquina con chat funcional, RAG, herramientas y panel de admin.

Tiempo estimado: 15-20 minutos en una máquina limpia.

---

## 1. Requisitos previos

Comprueba que tienes instalado: python 3.12+, node 20+, docker 24+, git.

Opcional: Ollama (ollama.ai) — LLM local como último fallback.

---

## 2. Clonar el repositorio

git clone https://github.com/Genfi07/ELI-Enhanced-Learning-Intelligence.git
cd ELI-Enhanced-Learning-Intelligence

---

## 3. Preparar el backend

Crear entorno virtual: python -m venv .venv
Activar: source .venv/bin/activate

Instalar dependencias: pip install -e "backend[dev]"

Copiar variables de entorno: cp backend/.env.example backend/.env

Edita backend/.env:
- Obligatorio: deja ELI_DATABASE_URL como está.
- Para chat real: rellena al menos una API key de LLM. La más sencilla es Groq (gratis): crea una key en console.groq.com/keys y pégala en ELI_OPENAI_API_KEY.

---

## 4. Preparar el frontend

cd frontend
npm install
cd ..

---

## 5. Arrancar todo

Terminal 1 — servicios base: ./start.sh

Terminal 2 — backend: ./run-backend.sh

Abrir en el navegador: http://localhost:3000/chat

Regístrate con cualquier email y contraseña (mínimo 8 caracteres).

---

## 6. Primer recorrido

- Chatea con ELI: ¿Qué hora es en Tokio?
- Pídele buscar: Busca en internet las noticias tech de esta semana
- Sube un PDF arrastrándolo al chat
- Pega una imagen con Ctrl+V
- Explora los flujos en /tools
- Panel admin en /admin

---

## 7. Promoción a SUPER_ADMIN

Ejecuta en el terminal:

docker exec -it infra-postgres-1 psql -U eli -d eli -c "UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'SUPER_ADMIN') WHERE email = 'tu-email@example.com';"

---

## 8. Problemas comunes

- Permiso requerido admin.config: tu usuario no es ADMIN.
- Postgres no arranca: revisa cd infra && docker compose logs.
- Frontend no recarga: rm -rf frontend/.next.

---

## 9. Siguientes pasos

- Ver ARCHITECTURE.md
- Ver API.md
- Correr tests: cd backend && pytest