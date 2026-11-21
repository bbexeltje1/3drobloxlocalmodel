@echo off
cd /d "%~dp0\.."
echo [RoForge 3D] Starting Local Roblox Multi-View 3D Asset Creator on http://127.0.0.1:8000 ...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
