#!/usr/bin/env bash
# ELI - Script de parada
# Uso: ./stop.sh

echo "Deteniendo ELI..."

pkill -f "uvicorn app.main" >/dev/null 2>&1 || true
pkill -f "next dev" >/dev/null 2>&1 || true
pkill -f "next-server" >/dev/null 2>&1 || true

cd "$(dirname "$0")/infra"
docker compose down >/dev/null 2>&1 || true

echo "✓ Detenido. (Ollama sigue corriendo en background)"
