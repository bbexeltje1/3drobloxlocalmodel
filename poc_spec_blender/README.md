# RoForge Spec → Blender MCP PoC

An isolated, local-first proof of concept for the Gobble Rail workflow: **brief/reference images → reviewable JSON spec → named Blender parts with exact materials → GLB**. All PoC code is in this folder. It does not change the existing RoForge app.

## Important connection boundary

Arena's remote workspace cannot open a socket to Blender on your Windows PC. Run this PoC's FastAPI app **on the same Windows PC as Blender**. It starts the MCP client process itself using your configured `uvx.exe` and the `mcp-for-blender` package, then talks to the Blender add-on over its loopback socket. The app listens only on `127.0.0.1:8765`; no tunnel, public listener, or firewall exposure is needed.

MCP for Blender has a local Blender add-on socket server and a separate MCP server process that speaks stdio to an MCP client. This PoC uses the supported stdio MCP route; it does not attempt to connect Arena directly to port 9876. See the [MCP for Blender quickstart](https://github.com/ahujasid/mcp-for-blender/blob/main/README.md#quickstart), [components](https://github.com/ahujasid/mcp-for-blender/blob/main/README.md#components), and [tool list](https://github.com/ahujasid/mcp-for-blender/blob/main/README.md#capabilities).

## Windows steps

1. **Open Blender 5.2.** Confirm `Interface: MCP for Blender` is enabled. In the 3D View press `N`, open the **MCP for Blender** tab, and start its server if it is stopped.
2. In PowerShell, from the repository folder, run:

   ```powershell
   .\poc_spec_blender\run_windows.ps1
   ```

   The first run creates this PoC's `.venv` and installs its Python requirements. It uses `C:\Users\MB\.local\bin\uvx.exe` if present; otherwise it looks for `uvx` on PATH. It does **not** launch a separate MCP client elsewhere. Keep this terminal open.
3. On that same PC, open **http://127.0.0.1:8765**.
4. Click **Test Blender MCP**. The app only reports connected after the stdio server starts, the expected tools are listed, and `get_addon_status` returns a response. The test does not create or edit objects.
5. Review the JSON. Check the explicit approval box, then click **Build in Blender**. The app sends deterministic Blender Python through `execute_blender_code`.

If PowerShell blocks the local script, use a one-process bypass (it does not change the machine-wide policy):

```powershell
powershell -ExecutionPolicy Bypass -File .\poc_spec_blender\run_windows.ps1
```

The standalone socket check can help diagnose a stopped add-on, but **is not** the app-level MCP handshake:

```powershell
Test-NetConnection 127.0.0.1 -Port 9876
```

Do not launch `uvx mcp-for-blender` in a second terminal or another MCP client while using this PoC. The app owns the one local stdio child for its lifetime. Stop the app with **Ctrl+C**.

### Add-on version caution

You reported add-on version **1.8**. The current upstream add-on source reports version **2.0** and protocol version **16**, so compatibility with your installed add-on is not yet verified. The app's real status handshake is the gate; if it reports a protocol/tool error, stop there rather than retrying generation. Review the official project's [upgrade instructions](https://github.com/ahujasid/mcp-for-blender/blob/main/README.md#upgrading-existing-users) before choosing whether to update. Its documented `uvx mcp-for-blender@latest update` flow keeps backups, but this PoC will not run an update or replace your add-on automatically.

## What the PoC builds

The starter JSON transcribes the supplied Gobble Rail specification where legible: proportion `10:4.8:2.6`, 13 primary feathers, 8 cranberry-can ribs, a 10–12 row range (starter uses 10 and marks it provisional), 2 pie-coil rings, and the six supplied palette hex values. The remaining details shown in the references are visual interpretations, **not measured facts**.

The generated scene has a dedicated `RoForge_GobbleRail_POC` collection and separately named Blender objects/materials. Material base colors come from the JSON palette. Feather count is controlled by the spec. Trigger, magazine, and wattle are separate objects with provisional pivot empties and motion metadata. Blender exports only the PoC collection to a GLB in `poc_spec_blender/outputs/` (or `POC_OUTPUT_DIR`); the app intentionally does **not** save or overwrite the user's open `.blend` file.

The exact dimensions in the screenshot are proportions, not a total Roblox stud measurement. `unit_mode` is therefore `normalized`; the user must set the final scale before Roblox import. Motion pivots and geometry are draft blockout interpretations. This PoC does not yet rig Roblox constraints or provide production topology/UVs/PBR maps.

## Optional local vision-language model

The JSON editor and supplied starter spec work without any model downloads. For image-and-text drafting on this hardware, start with **Ollama `qwen2.5vl:3b`**: Ollama lists it as a 3.2 GB model with image input. [Ollama model page](https://ollama.com/library/qwen2.5vl:3b) That is the model download size, **not** a promise that every image/context configuration fits fully in 6 GB VRAM; Ollama may use system RAM and run slower. Keep the reference images small and draft the spec before starting a heavy Blender task.

Install Ollama separately, then in PowerShell pull the model:

```powershell
ollama pull qwen2.5vl:3b
```

Keep the Ollama app/service running. If it is not already running, start `ollama serve` in its own terminal. In a **second PowerShell window**, configure the PoC to use Ollama's local API and launch the app:

```powershell
$env:POC_VLM_PROVIDER = 'ollama'
$env:POC_VLM_URL = 'http://127.0.0.1:11434/api/chat'
$env:POC_VLM_MODEL = 'qwen2.5vl:3b'
.\poc_spec_blender\run_windows.ps1
```

The PoC also accepts an OpenAI-compatible local vision endpoint by setting `POC_VLM_PROVIDER='openai'` and pointing `POC_VLM_URL` at `/v1/chat/completions`. The backend rejects non-loopback endpoints, so reference images cannot be sent to a cloud URL by configuration mistake. The model only drafts JSON; it does not execute Blender code. Each draft starts unapproved and must be reviewed. Without a configured endpoint, edit the included Gobble Rail JSON manually. A model's visual estimates are not measurements.

## Configuration

- `BLENDER_MCP_COMMAND`: full path to `uvx.exe`; default is `$USERPROFILE\.local\bin\uvx.exe` when present, else `uvx` from PATH.
- `BLENDER_MCP_ARGS`: JSON string array, default `["mcp-for-blender"]` (normally leave unchanged).
- `BLENDER_HOST` / `BLENDER_PORT`: default `localhost` / `9876`.
- `BLENDER_MCP_TIMEOUT`: tool timeout in seconds, default `180`.
- `POC_OUTPUT_DIR`: local output directory; default `poc_spec_blender/outputs`.
- `POC_VLM_PROVIDER`: `ollama` for Ollama's `/api/chat`, or `openai` for a local OpenAI-compatible endpoint (default `openai`).
- `POC_VLM_URL` / `POC_VLM_MODEL`: optional local vision-language endpoint/model.

The MCP subprocess receives only normal OS runtime environment variables and the Blender host/port—not unrelated environment variables or tokens. Keep the add-on on loopback. The local app rejects cross-origin write requests and binds to loopback.

## Testing

From the repository root:

```powershell
python -m unittest discover -s poc_spec_blender\tests -v
```

Tests check spec validation and compile the generated Blender Python script without requiring Blender/MCP. A passing test does **not** prove Blender is connected. That is verified only by the app's live **Test Blender MCP** button on your PC.
