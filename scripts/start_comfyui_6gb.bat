@echo off
REM ============================================================================
REM RoForge 3D — Launch ComfyUI Tuned for 6 GB VRAM + 32 GB System RAM
REM ============================================================================
REM Supports BOTH:
REM   1. Standard git clone  : C:\ComfyUI\main.py
REM   2. Windows Portable 7z : C:\ComfyUI_windows_portable\ComfyUI\main.py
REM ============================================================================

if "%COMFYUI_PATH%"=="" (
    if exist "C:\ComfyUI\main.py" (
        set "COMFYUI_PATH=C:\ComfyUI"
    ) else if exist "C:\ComfyUI_windows_portable\ComfyUI\main.py" (
        set "COMFYUI_PATH=C:\ComfyUI_windows_portable"
    ) else (
        set "COMFYUI_PATH=C:\ComfyUI"
    )
)

set "FLAGS=--lowvram --disable-pinned-memory --reserve-vram 1.0 --cache-none --listen 127.0.0.1 --port 8188"

if exist "%COMFYUI_PATH%\python_embeded\python.exe" (
    echo [RoForge 3D] Detected ComfyUI Windows Portable at %COMFYUI_PATH%
    cd /d "%COMFYUI_PATH%"
    "%COMFYUI_PATH%\python_embeded\python.exe" -s ComfyUI\main.py %FLAGS%
) else if exist "%COMFYUI_PATH%\ComfyUI\main.py" (
    echo [RoForge 3D] Launching ComfyUI from %COMFYUI_PATH%\ComfyUI
    cd /d "%COMFYUI_PATH%\ComfyUI"
    python main.py %FLAGS%
) else (
    echo [RoForge 3D] Launching ComfyUI from %COMFYUI_PATH%
    cd /d "%COMFYUI_PATH%"
    python main.py %FLAGS%
)
pause
