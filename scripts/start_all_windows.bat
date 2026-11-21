@echo off
setlocal

REM Double-click this file to start ComfyUI and the RoForge 3D web app in
REM separate command windows. ComfyUI path detection and low-VRAM flags are
REM handled by start_comfyui_6gb.bat.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

if not exist "%PROJECT_DIR%\backend\main.py" (
    echo [RoForge 3D] Could not find the project at "%PROJECT_DIR%".
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%start_comfyui_6gb.bat" (
    echo [RoForge 3D] Missing scripts\start_comfyui_6gb.bat.
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%start_creator.bat" (
    echo [RoForge 3D] Missing scripts\start_creator.bat.
    pause
    exit /b 1
)

echo [RoForge 3D] Opening ComfyUI and Creator UI in separate terminals...
start "RoForge 3D - ComfyUI" "%ComSpec%" /k call "%SCRIPT_DIR%start_comfyui_6gb.bat"
start "RoForge 3D - Creator UI" "%ComSpec%" /k call "%SCRIPT_DIR%start_creator.bat"

echo [RoForge 3D] Opening http://127.0.0.1:8000 in your browser...
timeout /t 8 /nobreak >nul
start "" "http://127.0.0.1:8000"
endlocal
