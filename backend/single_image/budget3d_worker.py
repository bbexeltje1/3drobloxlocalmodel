"""One-shot, offline Budget3D worker using the official repository model/sampler/decoder APIs."""
from __future__ import annotations

import gc
import os
import sys
import traceback
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 7:
        print("usage: budget3d_worker.py REPO CHECKPOINT IMAGE OUTPUT BUDGET SEED", file=sys.stderr)
        return 2
    repo, checkpoint, image_path, output_path = map(Path, sys.argv[1:5])
    budget, seed = float(sys.argv[5]), int(sys.argv[6])
    sys.path.insert(0, str(repo.resolve()))
    try:
        import torch
        from budget3d.models.load import decode_gaussians, idol_weights_dir, load_budget3d, load_decoders
        from budget3d.sampling.sampler import ImagePreprocessor, sample
    except Exception as exc:
        print(f"Official Budget3D/Idol modules unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    if not torch.cuda.is_available():
        print("CUDA is unavailable; refusing CPU fallback.", file=sys.stderr)
        return 4
    device = "cuda"
    props = torch.cuda.get_device_properties(0)
    print(f"CUDA device: {torch.cuda.get_device_name(0)}; total VRAM: {props.total_memory / 1024**3:.2f} GiB", flush=True)
    torch.cuda.empty_cache()
    try:
        weights = idol_weights_dir()
        print(f"Using cached/local Idol assets: {weights}", flush=True)
        # Sequentialize the officially implemented encoder and denoiser loads: compute the
        # exact official Idol conditioning first, release those weights, then load Budget3D.
        print("Loading official Idol image preprocessor and encoders…", flush=True)
        preprocessor = ImagePreprocessor(weights, device, "real")
        prepared, cond = preprocessor(str(image_path))
        prepared.save(str(output_path.with_name(output_path.stem + "_input.png")))
        del preprocessor
        gc.collect()
        torch.cuda.empty_cache()
        print("Image conditioning ready; preprocessor weights released.", flush=True)

        print("Loading local Budget3D checkpoint…", flush=True)
        model, step = load_budget3d(str(checkpoint), device=device, weights_dir=weights)
        print(f"Checkpoint loaded (step {step}); sampling at token budget {budget:.4g}…", flush=True)
        latent, camera, layout = sample(model, cond, budget=budget, steps=50, cfg=3.0,
                                       rescale_t=3.0, seed=seed, device=device, warmup_steps=0)
        print("Sampling complete; releasing denoiser and conditioning before decoder load.", flush=True)
        latent = latent.detach().to("cpu")
        del cond, model, camera, layout
        gc.collect()
        torch.cuda.empty_cache()

        print("Loading official Idol Gaussian decoders…", flush=True)
        decoder, gaussian_decoder, config = load_decoders(weights, device=device)
        print("Decoding Gaussian representation…", flush=True)
        representation = decode_gaussians(latent.to(device), decoder, gaussian_decoder, config, num_gaussians=262144)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        representation.save_ply(str(output_path))
        del representation, decoder, gaussian_decoder, latent
        gc.collect()
        torch.cuda.empty_cache()
        print(f"Wrote Budget3D Gaussian PLY: {output_path}", flush=True)
        return 0
    except Exception as exc:
        print(f"Budget3D inference failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
