"""Lazy, thread-safe loading of the Hugging Face classifiers + class-activation maps.

Models (verified by loading and running them, see docs in the final report):
  * deepfake     : prithivMLmods/deepfake-detector-model-v1  (SigLIP-base, 224px, labels {0: Fake, 1: Real})
  * ai_generated : haywoodsloan/ai-image-detector-deploy      (SwinV2, 256px, labels {0: artificial, 1: real})
Both can be overridden with ML_DEEPFAKE_MODEL / ML_AIGEN_MODEL (any HF image-classification model
whose labels look like fake/real; the mapping below is resolved from id2label at load time).

Explainability: both heads are "mean-pool tokens -> linear", so the (fake - real) logit decomposes
exactly into per-token contributions: CAM_t = h_t . (w_fake - w_real). This is an exact class
activation map (no gradients needed). For heads where that identity doesn't hold we skip the CAM.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

import numpy as np

from ..utils import deep_enabled, model_cache_dir

log = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "deepfake": "prithivMLmods/deepfake-detector-model-v1",
    "ai_generated": "haywoodsloan/ai-image-detector-deploy",
}
ENV_OVERRIDES = {"deepfake": "ML_DEEPFAKE_MODEL", "ai_generated": "ML_AIGEN_MODEL"}
FAKE_LABEL_RE = re.compile(r"fake|deepfake|artificial|^ai$|ai[_\s-]?gen|generated|synthetic|spoof|manipulated")
REAL_LABEL_RE = re.compile(r"real|human|^hum$|authentic|natural|genuine|original|bonafide|realism")
RETRY_AFTER_S = 60.0
# One global lock for loading: transformers' lazy imports are not safe when two threads trigger
# them at the same time, and loading two models at once only doubles peak memory anyway.
_LOAD_LOCK = threading.RLock()
BACKBONE_ATTRS = ("vision_model", "swinv2", "swin", "vit", "convnext", "efficientnet", "deit", "beit")


def model_id(key: str) -> str:
    return os.environ.get(ENV_OVERRIDES[key]) or DEFAULT_MODELS[key]


def resolve_fake_index(id2label: dict) -> int | None:
    labels = {int(k): str(v).strip().lower() for k, v in id2label.items()}
    fake = [i for i, l in labels.items() if FAKE_LABEL_RE.search(l) and not REAL_LABEL_RE.search(l)]
    if len(fake) == 1:
        return fake[0]
    real = [i for i, l in labels.items() if REAL_LABEL_RE.search(l) and not FAKE_LABEL_RE.search(l)]
    if len(labels) == 2 and len(real) == 1:
        return [i for i in labels if i != real[0]][0]
    return None


class DeepModel:
    def __init__(self, key: str):
        self.key = key
        self.lock = _LOAD_LOCK              # guards loading (shared by all models)
        self.infer_lock = threading.Lock()  # serialise inference (CPU-bound anyway, avoids thread oversubscription)
        self.model = None
        self.processor = None
        self.fake_idx: int | None = None
        self.real_idx: int | None = None
        self.labels: dict = {}
        self.error: str | None = None
        self.failed_at: float = 0.0
        self.cam_ok = False
        self.backbone = None
        self.id = model_id(key)

    @property
    def available(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        if self.model is not None:
            return True
        with self.lock:
            if self.model is not None:
                return True
            if self.failed_at and time.time() - self.failed_at < RETRY_AFTER_S:
                return False
            self.id = model_id(self.key)
            try:
                import torch  # noqa: F401
                from transformers import AutoImageProcessor, AutoModelForImageClassification
                cache = model_cache_dir()
                try:   # fast path: already in the cache, no network round-trips
                    proc = AutoImageProcessor.from_pretrained(self.id, cache_dir=cache, local_files_only=True,
                                                              use_fast=False)
                    model = AutoModelForImageClassification.from_pretrained(self.id, cache_dir=cache,
                                                                            local_files_only=True)
                except Exception:
                    proc = AutoImageProcessor.from_pretrained(self.id, cache_dir=cache, use_fast=False)
                    model = AutoModelForImageClassification.from_pretrained(self.id, cache_dir=cache)
                model.eval()
                fake_idx = resolve_fake_index(model.config.id2label)
                if fake_idx is None:
                    raise RuntimeError(f"cannot map labels {model.config.id2label} to fake/real")
                self.labels = {int(k): v for k, v in model.config.id2label.items()}
                self.fake_idx = fake_idx
                self.real_idx = None
                if len(self.labels) == 2:
                    self.real_idx = [i for i in self.labels if i != fake_idx][0]
                self.processor, self.model = proc, model
                self._setup_cam()
                self.error = None
                log.info("Loaded %s model %s (labels=%s, cam=%s)", self.key, self.id, self.labels, self.cam_ok)
                return True
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"[:300]
                self.failed_at = time.time()
                log.warning("Could not load %s model %s: %s", self.key, self.id, self.error)
                return False

    def _setup_cam(self) -> None:
        """Check that logits == classifier(mean(last_hidden_state)) so the exact CAM is valid."""
        import torch
        self.cam_ok = False
        self.backbone = None
        head = getattr(self.model, "classifier", None)
        if not isinstance(head, torch.nn.Linear):
            return
        for attr in BACKBONE_ATTRS:
            bb = getattr(self.model, attr, None)
            if bb is not None:
                self.backbone = bb
                break
        if self.backbone is None:
            return
        try:
            size = self.processor.size
            h = size.get("height") or size.get("shortest_edge") or 224
            w = size.get("width") or size.get("shortest_edge") or 224
            x = torch.randn(1, 3, int(h), int(w))
            with torch.inference_mode():
                ref = self.model(pixel_values=x).logits
                hs = self.backbone(pixel_values=x).last_hidden_state
                if hs.dim() != 3:
                    return
                mine = head(hs.mean(dim=1))
            self.cam_ok = bool(torch.allclose(ref, mine, atol=1e-3, rtol=1e-3))
        except Exception as exc:
            log.info("CAM disabled for %s: %s", self.id, exc)
            self.cam_ok = False

    def predict(self, images: list) -> tuple[list[float], list[np.ndarray | None]]:
        """images: list of PIL RGB images. Returns (fake probabilities, CAM grids or None)."""
        import torch
        if not self.load():
            raise RuntimeError(self.error or "model unavailable")
        with self.infer_lock, torch.inference_mode():
            inputs = self.processor(images=images, return_tensors="pt")
            pv = inputs["pixel_values"]
            cams: list[np.ndarray | None] = [None] * len(images)
            if self.cam_ok:
                hs = self.backbone(pixel_values=pv).last_hidden_state          # (B, N, C)
                head = self.model.classifier
                logits = head(hs.mean(dim=1))
                w = head.weight[self.fake_idx]
                if self.real_idx is not None:
                    w = w - head.weight[self.real_idx]
                contrib = (hs @ w).cpu().numpy()                               # (B, N)
                n = contrib.shape[1]
                side = int(round(n ** 0.5))
                if side * side == n:
                    cams = [c.reshape(side, side).astype(np.float32) for c in contrib]
            else:
                logits = self.model(pixel_values=pv).logits
            probs = torch.softmax(logits.float(), dim=-1)[:, self.fake_idx].cpu().numpy()
        return [float(p) for p in probs], cams


_registry: dict[str, DeepModel] = {}
_reg_lock = threading.Lock()


def get_model(key: str) -> DeepModel:
    with _reg_lock:
        m = _registry.get(key)
        if m is None or (m.model is None and m.id != model_id(key)):
            m = DeepModel(key)
            _registry[key] = m
        return m


def warmup_all() -> dict:
    status = {}
    if not deep_enabled():
        return {k: "disabled" for k in DEFAULT_MODELS}
    try:
        import torch
        # Keep a few cores for the web server; torch defaults to all cores.
        torch.set_num_threads(max(1, min(8, (os.cpu_count() or 2))))
    except Exception:
        pass
    for key in DEFAULT_MODELS:
        m = get_model(key)
        status[key] = "loaded" if m.load() else f"unavailable: {m.error}"
    return status


def models_loaded() -> bool:
    return all(get_model(k).available for k in DEFAULT_MODELS)
