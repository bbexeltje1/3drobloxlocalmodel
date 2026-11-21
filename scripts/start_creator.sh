#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
echo "[RoForge 3D] Starting Local Roblox Multi-View 3D Asset Creator on http://0.0.0.0:8000 ..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
