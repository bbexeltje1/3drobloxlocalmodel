@echo off
setlocal

REM Install the public ComfyUI-Idol nodes and missing weights without HF login/token.
REM Does not replace ComfyUI's Python/Torch and does not update ComfyUI itself.
set "IDOL_NODE_COMMIT=4d3a4f671028f0e062d9f004cda1a2dd73360d35"

if not defined COMFYUI_PATH (
    if exist "C:\ComfyUI\main.py" (
        set "COMFYUI_PATH=C:\ComfyUI"
    ) else if exist "C:\ComfyUI_windows_portable\ComfyUI\main.py" (
        set "COMFYUI_PATH=C:\ComfyUI_windows_portable\ComfyUI"
    ) else (
        echo [ComfyUI-Idol] Could not find ComfyUI. Set COMFYUI_PATH to its folder and retry.
        echo Example: set COMFYUI_PATH=C:\ComfyUI
        pause
        exit /b 1
    )
)

if exist "%COMFYUI_PATH%\ComfyUI\main.py" set "COMFYUI_PATH=%COMFYUI_PATH%\ComfyUI"
if not exist "%COMFYUI_PATH%\main.py" (
    echo [ComfyUI-Idol] No main.py found in "%COMFYUI_PATH%".
    echo Set COMFYUI_PATH to the actual ComfyUI folder, not the portable parent folder.
    pause
    exit /b 1
)

where git >nul 2>nul || (echo [ComfyUI-Idol] Git for Windows is required.& pause & exit /b 1)
where python >nul 2>nul || (echo [ComfyUI-Idol] Python 3 with pip is required for the public model downloader.& pause & exit /b 1)

set "IDOL_NODE=%COMFYUI_PATH%\custom_nodes\ComfyUI-Idol"
if not exist "%COMFYUI_PATH%\custom_nodes" mkdir "%COMFYUI_PATH%\custom_nodes"
if not exist "%IDOL_NODE%\.git" (
    if exist "%IDOL_NODE%" (
        echo [ComfyUI-Idol] "%IDOL_NODE%" exists but is not a Git checkout. Move it aside, then retry.
        pause
        exit /b 1
    )
    git clone https://github.com/Nynxz/ComfyUI-Idol.git "%IDOL_NODE%" || (pause & exit /b 1)
)
git -C "%IDOL_NODE%" fetch --depth 1 origin "%IDOL_NODE_COMMIT%" || (pause & exit /b 1)
git -C "%IDOL_NODE%" checkout --detach "%IDOL_NODE_COMMIT%" || (pause & exit /b 1)

python -m pip install --upgrade huggingface_hub || (pause & exit /b 1)
python "%~dp0download_models_6gb.py" --profile idol --comfy-dir "%COMFYUI_PATH%" || (pause & exit /b 1)

echo.
echo [ComfyUI-Idol] Setup complete. Models were downloaded anonymously; no HF account or token was used.
echo Restart ComfyUI before selecting ComfyUI Idol in RoForge.
echo Idol returns a Gaussian PLY. Mesh extraction is best-effort and may be rough or fail on 6 GB VRAM.
echo This installer does not upgrade ComfyUI; if the custom nodes are missing, update ComfyUI manually first.
pause
