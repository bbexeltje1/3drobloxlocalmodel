# Single Image → 3D local pipeline

This mode is additive; the existing Pixal3D, Hunyuan3D and multiview/optimizer paths are unchanged. The FastAPI process orchestrates one-shot worker processes so `nobg`/PyTorch and Budget3D/Idol dependencies are not imported into the main app.

## Local paths and isolated Python environments

Set these variables in the shell that launches RoForge (no model files are copied or downloaded):

```powershell
$env:FEYNOBG_MODEL_DIR = 'C:\Users\MB\FeyNobg'
# Point at the Python where the already-installed `nobg` package and compatible PyTorch are available.
$env:FEYNOBG_PYTHON = 'C:\path\to\feynobg-venv\Scripts\python.exe'

$env:BUDGET3D_REPO = 'C:\path\to\existing\Budget3D-checkout'
$env:BUDGET3D_PYTHON = 'C:\path\to\budget3d-venv\Scripts\python.exe'
$env:BUDGET3D_CHECKPOINT = 'C:\Users\MB\weights\budget3d_idol.safetensors'
# Optional overrides if the already-cached encoder files live outside Budget3D's defaults.
$env:BUDGET3D_DINOV3 = 'C:\path\to\existing\weights\dinov3\vith16plus_lvd1689m'
# Default is the public FLUX.2-klein-4B repo; it is only resolved from local HF cache in offline mode.
# $env:BUDGET3D_FLUX2_VAE = 'black-forest-labs/FLUX.2-klein-4B'

# Only set after validating a Gaussian-aware converter against a Budget3D PLY.
# The value is a JSON argv array; {input} is the Gaussian PLY and {output} must be a triangle-mesh GLB.
$env:GAUSSIAN_MESH_CONVERTER = '["C:\\path\\to\\converter.exe","--input","{input}","--output","{output}"]'

# Optional Blender MCP launcher settings; no separate PoC web server or port is needed.
$env:BLENDER_MCP_COMMAND = 'C:\path\to\uvx.exe'
$env:BLENDER_MCP_ARGS = '["mcp-for-blender"]'
```

The UI's local configuration panel reports whether the expected files, official sampler script and configured Python interpreters exist. FeyNobg is loaded via `AutoModel.from_pretrained(local_dir)` and `AutoProcessor.from_pretrained(local_dir)` in the configured worker; offline environment flags prevent Hub downloads. Budget3D uses its official `load_budget3d`, `ImagePreprocessor`, `sample`, `load_decoders`, and `decode_gaussians` functions, with the same real-image mode, 50 steps, CFG 3, and local checkpoint as `scripts/sample.py`. Its offline preflight checks the released Idol denoiser/decoder/BiRefNet files, converted DINOv3 directory, and cached FLUX.2 VAE without loading GPU weights or downloading anything. Missing assets stop the run explicitly.

Budget3D's lowest documented token budget is 0.0625. The worker requires CUDA and does not silently run the sampler on CPU. It sequences the official components: compute Idol image conditioning and release the preprocessor/encoder before loading the denoiser; after sampling, move the small latent to CPU and release the denoiser before loading the decoders. It clears CUDA cache between stages. This is the lowest-memory orchestration implemented without changing model architecture. It does not enable `--fast` by default (the official option uses BF16/fused attention/`torch.compile`) and does not invent a CPU-offload switch. The decoded output still uses the official default 262,144 Gaussians, so a 6 GB card remains unverified and may OOM; failures include the worker's CUDA diagnostic output.

## Gaussian conversion is a required external adapter

Budget3D's output PLY contains Gaussian parameters, not polygon faces. RoForge never sends that file to the mesh optimizer. `GAUSSIAN_MESH_CONVERTER` must be a separately validated converter that understands the exact Budget3D PLY layout and writes a conventional triangle-mesh GLB. The adapter rejects point clouds and verifies finite vertices and triangle faces, and reports watertightness/components. SuGaR is not automatically selected because compatibility with this single-image Budget3D output has not been tested here.

If the converter is absent or fails, the job stops at **Gaussian → polygon mesh conversion**, preserves the original image, prepared input and Gaussian PLY, and does not claim a mesh or run the Roblox exporter.

## Blender MCP — same RoForge app, one address

RoForge's FastAPI app owns one `BlenderMCPClient` instance and exposes the Blender status check and optional mesh handoff on the same port as the creator UI (normally `http://127.0.0.1:8000`). No separate Blender PoC web server or port 8765 is required for this workflow. MCP launcher settings (`BLENDER_MCP_COMMAND`, `BLENDER_MCP_ARGS`, `BLENDER_HOST`, `BLENDER_PORT`) are read by that existing client. The MCP SDK is part of the root requirements.

The mesh handoff reuses the PoC's shared Blender script builder. It imports only a validated GLB/GLTF/OBJ into a temporary collection, inspects mesh count/triangles/bounds, exports a GLB, removes its temporary objects/collection and never saves the user's `.blend`. If the add-on/MCP server is unavailable, the job records the warning and continues with the validated pre-Blender mesh. Do not launch both web apps for this flow; use only RoForge.

## Outputs and tests

Each job is stored below `outputs/<job-id>/`; original upload, FeyNobg RGBA, Idol input, Gaussian PLY, converted mesh and final Roblox bundle are retained where that stage succeeds. `python -m unittest discover -s backend/single_image/tests -v` exercises image framing and mesh-vs-point-cloud validation without running model inference. Live model, GPU, conversion and Blender tests require the user's local environments and assets.
