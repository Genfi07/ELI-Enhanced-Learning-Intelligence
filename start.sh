#!/usr/bin/env bash
# ELI — Arranque de servicios base (Postgres, Ollama, Next.js).
#
# IMPORTANTE: NO arranca el backend (Uvicorn). El backend se arranca en
# su propia terminal para poder ver los logs en vivo y reiniciar con
# Ctrl+C cuando se toca código de backend.
#
# Uso:
#   Terminal 1: ./start.sh        (este script)
#   Terminal 2: ./run-backend.sh  (backend en foreground)
#
# Para detener todo: ./stop.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$ROOT/.logs"
mkdir -p "$LOGS_DIR"

echo "==============================================="
echo " Arrancando servicios base de ELI"
echo "==============================================="

# ------------------------------------------------------------------ #
# 1) Postgres
# ------------------------------------------------------------------ #
echo ""
echo "[1/4] Postgres..."
cd "$ROOT/infra"
docker compose down >/dev/null 2>&1 || true
docker rm -f infra-postgres-1 >/dev/null 2>&1 || true
docker compose up -d >/dev/null
echo "      esperando a que esté healthy..."
for i in {1..30}; do
    STATUS=$(docker compose ps --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | head -1 || echo "")
    if echo "$STATUS" | grep -q "healthy"; then
        echo "      ✓ Postgres healthy"
        break
    fi
    sleep 1
done

# ------------------------------------------------------------------ #
# 2) Ollama
# ------------------------------------------------------------------ #
echo ""
echo "[2/4] Ollama..."
pkill -f "ollama serve" >/dev/null 2>&1 || true
nohup ollama serve > "$LOGS_DIR/ollama.log" 2>&1 &
sleep 3
if curl -sf http://localhost:11434/api/tags >/dev/null; then
    echo "      ✓ Ollama corriendo"
else
    echo "      ✗ Ollama NO responde — revisa $LOGS_DIR/ollama.log"
    exit 1
fi

# ------------------------------------------------------------------ #
# 3) Frontend (Next.js)
# ------------------------------------------------------------------ #
echo ""
echo "[3/4] Frontend (Next.js)..."
pkill -f "next dev" >/dev/null 2>&1 || true
pkill -f "next-server" >/dev/null 2>&1 || true
cd "$ROOT/frontend"
nohup npm run dev > "$LOGS_DIR/next.log" 2>&1 &
echo "      esperando a que arranque..."
for i in {1..30}; do
    if curl -sf http://localhost:3000/ >/dev/null 2>&1; then
        echo "      ✓ Frontend corriendo en puerto 3000"
        break
    fi
    sleep 1
done

# ------------------------------------------------------------------ #
# 4) Estado
# ------------------------------------------------------------------ #
echo ""
echo "[4/4] Estado..."
echo ""
echo "==============================================="
echo " Servicios base corriendo"
echo "==============================================="
echo ""
echo " Faltan 2 pasos para tener ELI 100% operativo:"
echo ""
echo " 1) Abre OTRA terminal y arranca el backend:"
echo ""
echo "      ./run-backend.sh"
echo ""
echo " 2) Cuando arranque, abre:"
echo ""
echo "      https://literate-space-sniffle-p7j76j4jq4x26x5r-3000.app.github.dev/chat"
echo ""
echo " Logs de servicios base:"
echo "   tail -f $LOGS_DIR/next.log"
echo "   tail -f $LOGS_DIR/ollama.log"
echo ""
echo " Para detener todo: ./stop.sh"