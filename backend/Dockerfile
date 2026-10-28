# syntax=docker/dockerfile:1.7
# =============================================================================
# TruthLens backend — FastAPI + PyTorch (CPU) ML pipeline
#
#   docker build -t truthlens-backend ./backend
#   docker build --build-arg PRELOAD_MODELS=false -t truthlens-backend ./backend
# =============================================================================

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1 — builder: compile/install all Python deps into an isolated venv
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY requirements*.txt ./

# 1) Install torch/torchvision (if requested by requirements-ml.txt) strictly from
#    the CPU-only index so we never pull the multi-GB CUDA wheels.
# 2) Install everything else; the CPU index stays available as an extra index so
#    any transitive torch requirement is still satisfied by the CPU build.
RUN pip install --upgrade pip wheel setuptools \
 && touch requirements-ml.txt \
 && (grep -iE '^[[:space:]]*(torch|torchvision|torchaudio)([<>=!~ ;\[]|$)' requirements-ml.txt > /tmp/torch-reqs.txt || true) \
 && if [ -s /tmp/torch-reqs.txt ]; then \
        echo "Installing CPU torch:" && cat /tmp/torch-reqs.txt \
        && pip install --index-url "${TORCH_INDEX_URL}" -r /tmp/torch-reqs.txt; \
    fi \
 && pip install --extra-index-url "${TORCH_INDEX_URL}" -r requirements.txt \
 # OpenCV GUI build drags in libGL; make sure only the headless variant remains.
 && if pip show opencv-python >/dev/null 2>&1; then \
        pip uninstall -y opencv-python && pip install --force-reinstall --no-deps opencv-python-headless; \
    fi

# -----------------------------------------------------------------------------
# Stage 2 — runtime: slim image, non-root user, app code + optional model cache
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG PRELOAD_MODELS=true
ARG APP_UID=10001

# libglib2.0-0 / libgomp1: required by opencv-python-headless and torch CPU kernels.
# libgl1 is harmless and covers libraries that link the GUI OpenCV build.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid ${APP_UID} app \
 && useradd --system --uid ${APP_UID} --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STORAGE_DIR=/app/storage \
    MODEL_CACHE_DIR=/app/models_cache \
    HF_HOME=/app/models_cache/huggingface \
    TORCH_HOME=/app/models_cache/torch \
    HF_HUB_DISABLE_TELEMETRY=1 \
    PORT=8000 \
    UVICORN_WORKERS=1

WORKDIR /app
COPY --chown=app:app . /app
COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh \
 && mkdir -p /app/storage /app/models_cache \
 && chown -R app:app /app/storage /app/models_cache

USER app

# Optionally bake model weights into the image so the first analysis is fast and the
# container works offline. Never fails the build (missing script / no network).
RUN if [ "${PRELOAD_MODELS}" = "true" ]; then \
        if [ -f scripts/download_models.py ]; then \
            echo "Pre-downloading models into ${MODEL_CACHE_DIR} ..." \
            && (python scripts/download_models.py \
                || echo "WARNING: model pre-download failed; models will download on first use."); \
        else \
            echo "WARNING: scripts/download_models.py not found; skipping model pre-download."; \
        fi; \
    else \
        echo "PRELOAD_MODELS=${PRELOAD_MODELS}; skipping model pre-download."; \
    fi

EXPOSE 8000

# start-period is generous: on first boot the models may load/download.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
