#!/usr/bin/env bash
# ELI — Arranque del backend (Uvicorn) en foreground.
#
# Este script es para correr en su PROPIA terminal. Bloquea el prompt
# hasta que pulsas Ctrl+C. Los logs de Uvicorn se ven en vivo aquí.
#
# Uso:
#   Terminal 1: ./start.sh        (Postgres + Ollama + Next)
#   Terminal 2: ./run-backend.sh  (Uvicorn en foreground)

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==============================================="
echo " Arrancando backend ELI (Uvicorn)"
echo "==============================================="
echo ""

# Matar cualquier Uvicorn viejo antes de arrancar.
fuser -k -9 8000/tcp 2>/dev/null || true
pkill -9 -f "uvicorn app.main" 2>/dev/null || true
sleep 1

cd "$ROOT/backend"
source .venv/bin/activate

echo "Aplicando migraciones pendientes..."
alembic upgrade head

echo ""
echo "Arrancando Uvicorn (Ctrl+C para parar)..."
echo ""

exec uvicorn app.main:app --reload --port 8000 --host 0.0.0.0