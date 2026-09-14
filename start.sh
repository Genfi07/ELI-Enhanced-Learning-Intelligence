#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$ROOT/.logs"
mkdir -p "$LOGS_DIR"

echo "=== Arrancando ELI ==="

echo "[1/5] Postgres..."
cd "$ROOT/infra"
docker compose down >/dev/null 2>&1 || true
docker rm -f infra-postgres-1 >/dev/null 2>&1 || true
docker compose up -d >/dev/null
sleep 8
echo "      ✓ Postgres"

echo "[2/5] Ollama..."
pkill -f "ollama serve" >/dev/null 2>&1 || true
nohup ollama serve > "$LOGS_DIR/ollama.log" 2>&1 &
sleep 3
echo "      ✓ Ollama"

echo "[3/5] Backend..."
pkill -f "uvicorn app.main" >/dev/null 2>&1 || true
cd "$ROOT/backend"
source .venv/bin/activate
nohup uvicorn app.main:app --reload --port 8000 --host 0.0.0.0 > "$LOGS_DIR/uvicorn.log" 2>&1 &
sleep 6
echo "      ✓ Backend"

echo "[4/5] Frontend..."
pkill -f "next dev" >/dev/null 2>&1 || true
pkill -f "next-server" >/dev/null 2>&1 || true
cd "$ROOT/frontend"
nohup npm run dev > "$LOGS_DIR/next.log" 2>&1 &
sleep 12
echo "      ✓ Frontend"

echo "[5/5] Verificación..."
curl -s http://localhost:3000/api/v1/health || echo "FALLO"

echo ""
echo "================================"
echo " ELI corriendo"
echo "================================"
echo ""
echo " URL:  https://literate-space-sniffle-p7j76j4jq4x26x5r-3000.app.github.dev/chat"
echo ""
echo " Logs:"
echo "   tail -f $LOGS_DIR/uvicorn.log"
echo "   tail -f $LOGS_DIR/next.log"