
# ==============================================================================
# Installation & Setup
# ==============================================================================

# Install dependencies using uv package manager
install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.8.13/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync

# ==============================================================================
# Playground Targets
# ==============================================================================

# Launch local dev playground
playground:
	@echo "==============================================================================="
	@echo "| 🚀 Starting your agent playground...                                        |"
	@echo "|                                                                             |"
	@echo "| 💡 Try asking: What's the weather in San Francisco?                         |"
	@echo "|                                                                             |"
	@echo "| 🔍 IMPORTANT: Select the 'app' folder to interact with your agent.          |"
	@echo "==============================================================================="
	uv run adk web . --port 8501 --reload_agents

# ==============================================================================
# Frontend
# ==============================================================================

# Install frontend dependencies
frontend-install:
	cd frontend && npm install

# Start frontend dev server (port 3000, proxies to ADK on 8000)
frontend:
	cd frontend && npm run dev

# ==============================================================================
# Backend (ADK API Server)
# ==============================================================================

# Start ADK API server on port 8000 (REST + SSE for frontend)
backend:
	@echo "==============================================================================="
	@echo "| 🔧 Starting ADK API server on http://localhost:8000                          |"
	@echo "==============================================================================="
	uv run adk api_server . --port 8000

# ==============================================================================
# Dev (Backend + Frontend together)
# ==============================================================================

# Start both backend and frontend in separate windows (Windows)
dev:
	@echo Starting backend + frontend in separate windows...
	@echo Open http://localhost:3000 after both windows are up.
	start "ADK Backend (port 8000)" cmd /k "cd /d $(CURDIR) && uv run adk api_server . --port 8000"
	@ping -n 6 127.0.0.1 >nul 2>&1
	start "Frontend Dev (port 3000)" cmd /k "cd /d $(CURDIR)\frontend && npm run dev"

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

# Run unit and integration tests
test:
	uv sync --dev
	uv run pytest tests/unit && uv run pytest tests/integration

# ==============================================================================
# Agent Evaluation
# ==============================================================================

# Run agent evaluation using ADK eval
# Usage: make eval [EVALSET=tests/eval/evalsets/basic.evalset.json] [EVAL_CONFIG=tests/eval/eval_config.json]
eval:
	@echo "==============================================================================="
	@echo "| Running Agent Evaluation                                                    |"
	@echo "==============================================================================="
	uv sync --dev --extra eval
	uv run adk eval ./app $${EVALSET:-tests/eval/evalsets/basic.evalset.json} \
		$(if $(EVAL_CONFIG),--config_file_path=$(EVAL_CONFIG),$(if $(wildcard tests/eval/eval_config.json),--config_file_path=tests/eval/eval_config.json,))

# Run evaluation with all evalsets
eval-all:
	@echo "==============================================================================="
	@echo "| Running All Evalsets                                                        |"
	@echo "==============================================================================="
	@for evalset in tests/eval/evalsets/*.evalset.json; do \
		echo ""; \
		echo "▶ Running: $$evalset"; \
		$(MAKE) eval EVALSET=$$evalset || exit 1; \
	done
	@echo ""
	@echo "✅ All evalsets completed"

# Run code quality checks (codespell, ruff, ty)
lint:
	uv sync --dev --extra lint
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run ty check .