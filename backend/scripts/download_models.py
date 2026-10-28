#!/usr/bin/env python
"""Pre-download every model used by the TruthLens ML pipeline into MODEL_CACHE_DIR.

Usage (from the backend/ directory, e.g. in the Docker build):
    MODEL_CACHE_DIR=/app/models_cache python scripts/download_models.py

Downloads (~1.1 GB total):
  * OpenCV YuNet face detector  (~0.2 MB)  -> $MODEL_CACHE_DIR/opencv/
  * prithivMLmods/deepfake-detector-model-v1  (~372 MB)
  * haywoodsloan/ai-image-detector-deploy     (~781 MB)
Only the files needed by `from_pretrained` are fetched (not the training checkpoints in the repos).
Exits non-zero if something could not be downloaded, so a broken build is noticed.
"""
from __future__ import annotations

import os
import sys
import time

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)


def main() -> int:
    os.environ["ML_ENABLE_DEEP"] = "true"  # force the deep models on for downloading
    from app.ml.detectors import faces
    from app.ml.detectors.models import DEFAULT_MODELS, get_model
    from app.ml.utils import model_cache_dir

    cache = model_cache_dir()
    print(f"MODEL_CACHE_DIR = {cache}")
    ok = True

    p = faces.yunet_path(download=True)
    print(f"[faces] YuNet: {p or 'FAILED (Haar cascade fallback will be used)'}")
    ok &= bool(p)

    for key in DEFAULT_MODELS:
        t = time.time()
        m = get_model(key)
        if m.load():
            # one dummy inference so any lazily-fetched processor files are cached too
            from PIL import Image
            m.predict([Image.new("RGB", (64, 64), (128, 128, 128))])
            print(f"[{key}] {m.id}: OK in {time.time() - t:.1f}s labels={m.labels} cam={m.cam_ok}")
        else:
            print(f"[{key}] {m.id}: FAILED: {m.error}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
