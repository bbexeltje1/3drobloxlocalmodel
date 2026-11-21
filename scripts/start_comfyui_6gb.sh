#!/usr/bin/env bash
# ============================================================================
# RoForge 3D — Launch ComfyUI Tuned for 6 GB VRAM + 32 GB System RAM
# ============================================================================
set -e

COMFYUI_PATH="${COMFYUI_PATH:-$HOME/ComfyUI}"
echo "[RoForge 3D] Launching ComfyUI from $COMFYUI_PATH in 6 GB VRAM + 32 GB RAM Mode..."
cd "$COMFYUI_PATH"
python3 main.py \
  --lowvram \
  --disable-pinned-memory \
  --reserve-vram 1.0 \
  --cache-none \
  --listen 127.0.0.1 \
  --port 8188
