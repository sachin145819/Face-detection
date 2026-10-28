# =============================================================================
# TruthLens — developer shortcuts
# NOTE: the repo may live in a path containing spaces; every path below is quoted.
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
VENV         := $(BACKEND_DIR)/.venv
PY           := $(VENV)/bin/python
PYTHON       ?= python3
PY_VERSION   ?= 3.12
COMPOSE      ?= docker compose
COMPOSE_DEV  ?= docker compose -f docker-compose.dev.yml

# On Linux, pull CPU-only torch wheels (PyPI's Linux torch bundles multi-GB CUDA libs).
# macOS/Windows wheels on PyPI are already CPU/MPS builds.
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
  TORCH_INDEX_URL ?= https://download.pytorch.org/whl/cpu
endif
PIP_EXTRA := $(if $(TORCH_INDEX_URL),--extra-index-url $(TORCH_INDEX_URL),)
UV_EXTRA  := $(if $(TORCH_INDEX_URL),--extra-index-url $(TORCH_INDEX_URL) --index-strategy unsafe-best-match,)

# Load root .env (if any) for native dev runs; Compose reads it by itself.
LOAD_ENV := if [ -f .env ]; then set -a; . ./.env; set +a; fi

.PHONY: help setup setup-backend setup-frontend dev dev-backend dev-frontend test test-ml lint \
        build up down logs ps migrate models db-up db-down clean clean-all

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup -------
setup: setup-backend setup-frontend ## Create backend venv + install all deps
	@echo "Setup complete. Run 'make dev' to start backend + frontend."

setup-backend: ## Create backend/.venv (uv if available) and install requirements
	@if command -v uv >/dev/null 2>&1; then \
	  echo ">> using uv"; \
	  [ -x "$(PY)" ] || uv venv "$(VENV)" --python $(PY_VERSION); \
	  cd "$(BACKEND_DIR)" && uv pip install --python .venv/bin/python $(UV_EXTRA) -r requirements.txt; \
	else \
	  echo ">> uv not found, using $(PYTHON) -m venv"; \
	  [ -x "$(PY)" ] || $(PYTHON) -m venv "$(VENV)"; \
	  "$(PY)" -m pip install --upgrade pip; \
	  cd "$(BACKEND_DIR)" && .venv/bin/python -m pip install $(PIP_EXTRA) -r requirements.txt; \
	fi

setup-frontend: ## npm install in frontend/
	cd "$(FRONTEND_DIR)" && npm install

# ------------------------------------------------------------------ dev -------
dev-backend: ## Run FastAPI with auto-reload on :8000 (SQLite by default)
	@$(LOAD_ENV); cd "$(BACKEND_DIR)" && \
	  if [ -f alembic.ini ]; then .venv/bin/alembic upgrade head; fi && \
	  .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run Vite dev server on :5173 (proxies /api -> :8000)
	cd "$(FRONTEND_DIR)" && npm run dev

dev: ## Run backend + frontend together (Ctrl+C stops both)
	@trap 'kill 0' INT TERM EXIT; \
	  $(MAKE) --no-print-directory dev-backend & \
	  $(MAKE) --no-print-directory dev-frontend & \
	  wait

db-up: ## Start only PostgreSQL for local dev (localhost:5432)
	$(COMPOSE_DEV) up -d
	@echo "export DATABASE_URL=postgresql+psycopg://truthlens:truthlens@localhost:5432/truthlens"

db-down: ## Stop the local-dev PostgreSQL
	$(COMPOSE_DEV) down

migrate: ## Apply Alembic migrations (local venv)
	@$(LOAD_ENV); cd "$(BACKEND_DIR)" && .venv/bin/alembic upgrade head

models: ## Pre-download ML model weights into MODEL_CACHE_DIR
	@$(LOAD_ENV); cd "$(BACKEND_DIR)" && .venv/bin/python scripts/download_models.py

# ----------------------------------------------------------------- test -------
test: ## Run backend test-suite (fast: classical ML only)
	cd "$(BACKEND_DIR)" && ML_ENABLE_DEEP=$${ML_ENABLE_DEEP:-false} .venv/bin/python -m pytest -q

test-ml: ## Run tests with the deep models enabled (slow, needs weights)
	cd "$(BACKEND_DIR)" && ML_ENABLE_DEEP=true .venv/bin/python -m pytest -q

lint: ## Lint the frontend
	cd "$(FRONTEND_DIR)" && npm run lint

# --------------------------------------------------------------- docker -------
build: ## Build Docker images
	$(COMPOSE) build

up: ## Start the full stack in the background (http://localhost:8080)
	@[ -f .env ] || { echo ">> .env not found, copying .env.example"; cp .env.example .env; }
	$(COMPOSE) up -d --build
	@echo "TruthLens: http://localhost:$${FRONTEND_PORT:-8080}  |  API docs: http://localhost:$${BACKEND_PORT:-8000}/docs"

down: ## Stop the stack (keeps volumes)
	$(COMPOSE) down

logs: ## Follow container logs
	$(COMPOSE) logs -f --tail=200

ps: ## Show container status
	$(COMPOSE) ps

# ---------------------------------------------------------------- clean -------
clean: ## Remove caches and build output (keeps venv, node_modules, data)
	find "$(BACKEND_DIR)" -path "$(VENV)" -prune -o -type d \( -name __pycache__ -o -name .pytest_cache \) -print -exec rm -rf {} + 2>/dev/null || true
	rm -rf "$(FRONTEND_DIR)/dist"
	@echo "Tip: 'make clean-all' also removes venv, node_modules and local data."

clean-all: clean ## Also remove venv, node_modules, local DB/storage and Docker volumes
	rm -rf "$(VENV)" "$(FRONTEND_DIR)/node_modules" "$(BACKEND_DIR)/storage" "$(BACKEND_DIR)/truthlens.db"
	-$(COMPOSE) down -v
