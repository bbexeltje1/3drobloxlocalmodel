$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python 3.10+ is required. Install Python, reopen PowerShell, and run this script again."
    }
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.10 or newer is required."
    }
    python -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The PoC virtual environment uses Python older than 3.10. Remove poc_spec_blender\.venv and rerun with Python 3.10+."
}

& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "PoC dependency installation failed."
}

# The app launches the MCP stdio process when Test Blender MCP is clicked.
# Do not launch a second mcp-for-blender process manually.
$KnownUvx = Join-Path $env:USERPROFILE ".local\bin\uvx.exe"
if (Test-Path $KnownUvx) {
    $env:BLENDER_MCP_COMMAND = $KnownUvx
} elseif (Get-Command uvx -ErrorAction SilentlyContinue) {
    $env:BLENDER_MCP_COMMAND = (Get-Command uvx).Source
} else {
    throw "uvx was not found. Install or repair uv, or set BLENDER_MCP_COMMAND to the full path of uvx.exe."
}

if (-not $env:BLENDER_MCP_ARGS) { $env:BLENDER_MCP_ARGS = '["mcp-for-blender"]' }
if (-not $env:BLENDER_HOST) { $env:BLENDER_HOST = "localhost" }
if (-not $env:BLENDER_PORT) { $env:BLENDER_PORT = "9876" }
if (-not $env:POC_OUTPUT_DIR) { $env:POC_OUTPUT_DIR = Join-Path $ProjectRoot "outputs" }

Write-Host ""
Write-Host "RoForge Spec to Blender PoC" -ForegroundColor Green
Write-Host "MCP launcher: $env:BLENDER_MCP_COMMAND"
Write-Host "MCP args:     $env:BLENDER_MCP_ARGS"
Write-Host "Open locally: http://127.0.0.1:8765"
Write-Host "Keep Blender open with the MCP add-on server started. This app binds loopback only."
Write-Host "Press Ctrl+C to stop the local app."
Write-Host ""

Push-Location $ProjectRoot
try {
    & $VenvPython -m uvicorn app:app --app-dir $ProjectRoot --host 127.0.0.1 --port 8765
    if ($LASTEXITCODE -ne 0) {
        throw "The local PoC server exited with an error."
    }
} finally {
    Pop-Location
}
