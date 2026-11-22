# RoForge 3D — Local Multi-View Roblox 3D Asset Creator (6 GB VRAM + 32 GB RAM Edition)

A 100% local, privacy-preserving **Multi-View Image-to-3D Studio** purpose-built for **Roblox Studio** (`MeshPart` + `SurfaceAppearance` PBR) and specifically engineered for **6 GB VRAM GPUs paired with 32 GB System RAM**.

---

## Key Features

1. **Multi-View (2–4 Image) 3D Generation Wired for 6 GB VRAM + 32 GB RAM**
   - **ComfyUI `Pixal3D Multi-View` Bridge (`Comfy-Org/Pixal3D` INT8 / `Aero-Ex/Pixal3D-GGUF` Q4_K_M — MIT License)**: Automatically uploads your `Front`, `Left`, `Back`, and `Right` turnaround views and executes a custom 6 GB VRAM graph (`512³` sparse voxel grid, `384` remesh, `1024×1024` PBR bake) while offloading the ~12 GiB NAF multi-view feature cache safely into your **32 GB System RAM** via `--lowvram --disable-pinned-memory`.
   - **`Tencent Hunyuan3D-2mv` Low-VRAM Runner (`hunyuan3d-dit-v2-mv-turbo`)**: Direct Python FP16 shape generator (`octree_resolution=256`, ~4.5–5.5 GB VRAM) + zero-VRAM multi-view camera PBR projection.
   - **Instant CPU Multi-View Visual-Hull + PBR Sculptor (0 GB VRAM)**: Works immediately out-of-the-box on any machine for rapid silhouette blocking, sample turnaround testing, or headless servers.
   - **Raw `.glb` / `.obj` Mesh Optimizer**: Drop any 500,000-triangle AI mesh from ComfyUI / TRELLIS.2 / Blender to instantly decimate and unpack its textures for Roblox Studio.

2. **Strict Roblox Studio Geometry & Scale Compliance**
   - **Garland-Heckbert QEM Decimation (`fast-simplification`)** with one-click Roblox presets:
     - **UGC Rigid Accessory (Hat / Back / Waist)**: `3,600` tris (`≤ 4,000` Marketplace cap)
     - **Repeated Map Prop**: `2,400` tris
     - **Weapon / Held Tool**: `7,500` tris
     - **Hero MeshPart / Boss / Vehicle**: `15,000` tris (`< 21,000` Roblox `MeshPart` hard wall)
   - **Roblox Stud Scaling & Ground Pivot**: Scales bounding box to exact target **Roblox Studs** (`1 stud = 0.28 m`) and grounds bottom pivot at `Y = 0`.

3. **Automatic `SurfaceAppearance` PBR Texture Unpacking (`1024×1024` PNGs)**
   - Standard glTF `.glb` files pack Roughness (`G`) and Metalness (`B`) into a single texture, whereas Roblox `SurfaceAppearance` requires **4 separate image assets**.
   - Every export automatically outputs a single `.zip` bundle containing:
     - `<Asset>_roblox.glb` (full glTF 2.0 PBR for Roblox Studio 3D Importer)
     - `<Asset>_roblox.obj` (clean UV-mapped geometry)
     - `SurfaceAppearance/ColorMap.png` (dilation-padded albedo, zero mipmap seam bleed)
     - `SurfaceAppearance/NormalMap.png` (OpenGL `+Y` tangent-space normal map)
     - `SurfaceAppearance/MetalnessMap.png` (unpacked grayscale metallic map)
     - `SurfaceAppearance/RoughnessMap.png` (unpacked grayscale roughness map)
     - `setup_surface_appearance.lua` (Command Bar auto-setup script for Roblox Studio)

---

## Quick Start on Your Local PC (Windows / Linux)

### 1. Install Python Dependencies & Launch the Creator UI
```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Open `http://127.0.0.1:8000` in your browser. The **Single Image → 3D** mode is part of this same app and address; it does not require opening the separate Blender PoC web UI. Its optional Blender MCP status/inspection calls use the MCP client inside RoForge. Install the root requirements after pulling updates so the `mcp` SDK is present.

**Pipeline limitation:** Budget3D outputs Gaussian PLY data. Single Image → 3D intentionally stops at Gaussian-to-mesh conversion unless a compatible `GAUSSIAN_MESH_CONVERTER` is configured and verified; it will not treat the splat PLY as a mesh.

### 2. Enable Full AI `Pixal3D Multi-View` on 6 GB VRAM + 32 GB RAM
1. Install **ComfyUI (`>= 0.33.0`)**.
2. Download the MIT-licensed `Pixal3D` weights:
   ```bash
   python scripts/download_models_6gb.py --profile pixal3d --comfy-dir "C:/ComfyUI"
   ```
   *(Optional ultra-low VRAM Q4_K_M GGUF weights: add `--gguf` and install `Aero-Ex/ComfyUI-Trellis2-GGUF`)*
3. Launch ComfyUI using our **6 GB VRAM + 32 GB RAM launcher**:
   - **Windows**: `scripts\start_comfyui_6gb.bat`
   - **Linux**: `./scripts/start_comfyui_6gb.sh`
4. Click **Generate Roblox 3D Asset** in the web app — `Auto` mode will automatically detect ComfyUI on port `8188` and run `Pixal3DMultiViewConditioning`!
