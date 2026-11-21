@echo off
setlocal

REM Optional experimental single-image Budget3D-Idol-Turbo setup.
REM Kept in a separate venv so it cannot replace the Creator/ComfyUI PyTorch.
set "BUDGET3D_HOME=%USERPROFILE%\Budget3D"

where git >nul 2>nul || (echo [Budget3D] Git is required. Install Git for Windows first.& pause & exit /b 1)
where py >nul 2>nul || (echo [Budget3D] Python Launcher is required. Install Python 3.12 first.& pause & exit /b 1)

if not exist "%BUDGET3D_HOME%\scripts\sample.py" (
    if exist "%BUDGET3D_HOME%" (
        echo [Budget3D] The folder "%BUDGET3D_HOME%" exists but is not a Budget3D checkout.
        pause
        exit /b 1
    )
    git clone --depth 1 https://github.com/BudgetAny/Budget3D.git "%BUDGET3D_HOME%" || (pause & exit /b 1)
)

if not exist "%BUDGET3D_HOME%\third_party\idol-sdk\idol" (
    if exist "%BUDGET3D_HOME%\third_party\idol-sdk" rmdir /s /q "%BUDGET3D_HOME%\third_party\idol-sdk"
    git clone https://github.com/speridlabs/idol-sdk.git "%BUDGET3D_HOME%\third_party\idol-sdk" || (pause & exit /b 1)
    git -C "%BUDGET3D_HOME%\third_party\idol-sdk" checkout 956439f || (pause & exit /b 1)
)

if not exist "%BUDGET3D_HOME%\.venv\Scripts\python.exe" (
    py -3.12 -m venv "%BUDGET3D_HOME%\.venv" || (pause & exit /b 1)
)

call "%BUDGET3D_HOME%\.venv\Scripts\activate.bat"
python -m pip install --upgrade pip || (pause & exit /b 1)
python -m pip install -r "%BUDGET3D_HOME%\requirements.txt" || (pause & exit /b 1)

if not exist "%BUDGET3D_HOME%\weights" mkdir "%BUDGET3D_HOME%\weights"
hf download BudgetAny/Budget3D-Idol-Turbo budget3d_idol_turbo.safetensors config.json --local-dir "%BUDGET3D_HOME%\weights" || (pause & exit /b 1)

echo.
echo [Budget3D] Base setup complete. Before using the Idol option:
echo   1. Accept any required DINOv3 / FLUX.2 model access terms on Hugging Face.
echo   2. In this terminal run: hf auth login
echo   3. Convert the DINOv3 encoder with:
echo      cd /d "%BUDGET3D_HOME%"
echo      .venv\Scripts\python scripts\convert_dinov3_to_hf.py --model-name vith16plus_lvd1689m --save-dir weights\dinov3
echo   4. The first generation may download Idol's public decoder weights and the FLUX.2 VAE into the local Hugging Face cache.
echo.
echo Budget3D-Turbo is single-image and produces Gaussian-splat .PLY, NOT a Roblox mesh. Close ComfyUI before generation; a 6 GB GTX 1660 may still run out of VRAM.
pause
