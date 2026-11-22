"""Local metadata dispatch for the official ``nobg.AutoModel`` API."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator


def local_birefnet_tags(model_dir: Path) -> list[str]:
    """Identify the expected official FeyNobg architecture using local metadata only."""
    processor_config = json.loads((model_dir / "preprocessor_config.json").read_text(encoding="utf-8"))
    if processor_config.get("image_processor_type") != "BiRefNetImageProcessor":
        raise RuntimeError(
            "The configured FeyNobg folder does not identify the expected official "
            "BiRefNetImageProcessor in preprocessor_config.json."
        )
    return ["nobg-birefnet"]


@contextmanager
def local_model_info(auto_module, model_dir: Path, tags: list[str]) -> Iterator[None]:
    """Satisfy nobg's unconditional model_info dispatch without any Hub request."""
    original_model_info = auto_module.model_info

    def model_info_for_local_path(repo_id, *args, **kwargs):
        try:
            candidate = Path(os.fspath(repo_id)).resolve()
        except (TypeError, ValueError, OSError):
            candidate = None
        if candidate == model_dir:
            return SimpleNamespace(tags=tags)
        raise RuntimeError(f"Refusing non-local FeyNobg model identifier: {repo_id!r}")

    auto_module.model_info = model_info_for_local_path
    try:
        yield
    finally:
        auto_module.model_info = original_model_info
