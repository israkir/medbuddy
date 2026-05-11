# MedBuddy — common tasks (GNU Make). Run `make` or `make help`.
# Backend: `be-*`   Frontend (Expo): `fe-*`

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

BACKEND := apps/backend
FRONTEND := apps/frontend

PYTHON ?= python3
VENV := .venv
# Absolute paths so `cd $(BACKEND) && …` still finds the repo-root venv.
PIP := $(CURDIR)/$(VENV)/bin/pip
UVICORN := $(CURDIR)/$(VENV)/bin/uvicorn
PYTEST := $(CURDIR)/$(VENV)/bin/pytest
RUFF := $(CURDIR)/$(VENV)/bin/ruff
BLACK := $(CURDIR)/$(VENV)/bin/black

PORT ?= 8000

# Podman or Docker — `compose.yaml` and repo-root `Dockerfile` (context: `.`).
CONTAINER ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)
COMPOSE := $(CONTAINER) compose

# --- ANSI colors (256-color friendly) ---
NO   := \033[0m
BOLD := \033[1m
DIM  := \033[2m

RED    := \033[38;5;203m
ORANGE := \033[38;5;208m
GREEN  := \033[38;5;114m
TEAL   := \033[38;5;73m
BLUE   := \033[38;5;75m
PURPLE := \033[38;5;141m
PINK   := \033[38;5;212m

# Note: no leading @ inside defines — $(call) may run inside shell `if` / loops.
define banner
printf '%b\n' "$(PURPLE)$(BOLD)▶ $(1)$(NO)"
endef

define ok
printf '%b\n' "$(GREEN)$(BOLD)✓$(NO) $(1)"
endef

define warn
printf '%b\n' "$(ORANGE)$(BOLD)!$(NO) $(1)"
endef

.PHONY: help \
	be-venv be-install be-dev be-dev-mock be-dev-production be-run be-run-prod be-run-prod-production \
	be-test be-test-verbose be-test-cov be-lint be-fmt be-check \
	be-compose be-build be-clean be-clean-all \
	fe-install fe-dev fe-dev-mock fe-dev-api fe-build fe-run-ios fe-run-android fe-lint fe-check fe-test \
	pre-commit-install pre-commit-run

.DEFAULT_GOAL := help

##@ General

help: ## Show this help (default)
	@printf '%b\n' "$(TEAL)$(BOLD)MedBuddy$(NO) $(DIM)— pick a target$(NO) $(DIM)$(BACKEND) · $(FRONTEND)$(NO)"
	@printf '%b\n' ""
	@awk -v teal="$(TEAL)" -v bold="$(BOLD)" -v no="$(NO)" -v pink="$(PINK)" -v dim="$(DIM)" -v blue="$(BLUE)" ' \
	function trim(s) { gsub(/^[ \t]+|[ \t]+$$/, "", s); return s } \
	/^##@/ { \
		sub(/^##@[ \t]*/, ""); \
		printf "\n%s%s%s%s\n", teal, bold, $$0, no; \
		next \
	} \
	/^[a-zA-Z0-9_.-]+:.*##/ { \
		n = index($$0, "##"); \
		if (!n) next; \
		desc = trim(substr($$0, n + 2)); \
		colon = index($$0, ":"); \
		target = trim(substr($$0, 1, colon - 1)); \
		printf "  %s%-20s%s %s\n", pink, target, no, desc; \
		next \
	} \
	' $(MAKEFILE_LIST)
	@printf '%b\n' ""
	@printf '%b\n' "$(DIM)Backend:$(NO) $(BLUE)make be-install$(NO) -> $(BLUE)make be-dev$(NO) $(DIM)(mock)$(NO) or $(BLUE)make be-dev-production$(NO) $(DIM)(loads .env)$(NO) -> $(BLUE)make be-test$(NO)"
	@printf '%b\n' "$(DIM)Frontend:$(NO) $(BLUE)make fe-install$(NO) -> $(BLUE)make fe-dev$(NO) / $(BLUE)make fe-dev-api$(NO) $(DIM)(Expo)$(NO)"
	@printf '%b\n' "$(DIM)Git hooks:$(NO) $(BLUE)make pre-commit-install$(NO) $(DIM)(after be-install); $(BLUE)make pre-commit-run$(NO) $(DIM)(also runs fe-install for frontend hooks)$(NO)"

##@ Git hooks

pre-commit-install: be-install ## Install pre-commit hooks (repo-root .venv)
	@$(call banner,pre-commit install)
	@cd "$(CURDIR)" && "$(CURDIR)/$(VENV)/bin/pre-commit" install
	@$(call ok,pre-commit hooks installed)

pre-commit-run: be-install fe-install ## Run pre-commit on all files (skips changelog rule; git commit still requires CHANGELOG.md staged)
	@$(call banner,pre-commit run --all-files)
	@cd "$(CURDIR)" && SKIP=require-changelog-staged "$(CURDIR)/$(VENV)/bin/pre-commit" run --all-files
	@$(call ok,pre-commit finished)

##@ Backend — environment

be-venv: ## Create repo-root .venv if missing
	@if [ -d "$(CURDIR)/$(VENV)" ]; then \
		$(call warn,$(VENV) already exists - skipping); \
	else \
		$(call banner,Creating virtualenv with $(PYTHON)); \
		$(PYTHON) -m venv "$(CURDIR)/$(VENV)"; \
		$(call ok,venv ready); \
	fi

be-install: be-venv ## pip install -e apps/backend[dev]
	@$(call banner,pip install -e apps/backend[dev])
	@$(PIP) install -q -e "./$(BACKEND)[dev]"
	@$(call ok,dependencies installed)

##@ Backend — run API

# Force mock mode so repo/.env with MEDBUDDY_INTEGRATION=production does not affect local dev by mistake.
be-dev: be-dev-mock ## Uvicorn + reload (mock integrations; same as be-dev-mock)

be-dev-mock: be-install ## Uvicorn + reload, MEDBUDDY_INTEGRATION=mock
	@$(call banner,Uvicorn http://127.0.0.1:$(PORT) $(DIM)[mock · Ctrl+C]$(NO))
	@export MEDBUDDY_INTEGRATION=mock; \
	 export LINE_CHANNEL_SECRET=$${LINE_CHANNEL_SECRET:-}; \
	 $(UVICORN) medbuddy.main:app --reload --host 127.0.0.1 --port $(PORT)

be-dev-production: be-install ## Uvicorn + reload, production adapters (read LINE/Gemini/etc. from .env)
	@$(call warn,Using MEDBUDDY_INTEGRATION=production — ensure apps/backend/.env has tokens and keys)
	@$(call banner,Uvicorn http://127.0.0.1:$(PORT) $(DIM)[production · Ctrl+C]$(NO))
	@export MEDBUDDY_INTEGRATION=production; \
	 $(UVICORN) medbuddy.main:app --reload --host 127.0.0.1 --port $(PORT)

be-run: be-dev ## Alias for be-dev

be-run-prod: be-install ## Uvicorn without reload (mock)
	@$(call banner,Uvicorn no-reload http://127.0.0.1:$(PORT) $(DIM)[mock]$(NO))
	@export MEDBUDDY_INTEGRATION=mock; \
	 $(UVICORN) medbuddy.main:app --host 127.0.0.1 --port $(PORT)

be-run-prod-production: be-install ## Uvicorn without reload (production integrations)
	@$(call warn,Using MEDBUDDY_INTEGRATION=production — ensure apps/backend/.env is configured)
	@export MEDBUDDY_INTEGRATION=production; \
	 $(UVICORN) medbuddy.main:app --host 127.0.0.1 --port $(PORT)

##@ Backend — tests and quality

be-test: be-install ## Pytest (quiet)
	@$(call banner,pytest)
	@cd $(BACKEND) && $(PYTEST) -q
	@$(call ok,tests passed)

be-test-verbose: be-install ## Pytest verbose
	@$(call banner,pytest -v)
	@cd $(BACKEND) && $(PYTEST) -v --tb=short

be-test-cov: be-install ## Pytest with coverage
	@$(call banner,pytest --cov)
	@cd $(BACKEND) && $(PYTEST) -q --cov=medbuddy --cov-report=term-missing
	@$(call ok,coverage done)

be-lint: be-install ## Ruff check + black --check
	@$(call banner,ruff check)
	@$(RUFF) check $(BACKEND)/src $(BACKEND)/tests
	@$(call banner,black --check)
	@cd $(BACKEND) && $(BLACK) --check src tests

be-fmt: be-install ## Apply Black formatting
	@$(call banner,black)
	@cd $(BACKEND) && $(BLACK) src tests
	@$(call ok,formatted)

be-check: be-test be-lint ## Tests then lint

##@ Backend — containers

be-compose: ## Compose up API service (Podman or Docker — see CONTAINER)
	@$(call banner,$(COMPOSE) up --build)
	@$(COMPOSE) up --build

be-build: ## Build API OCI image (Podman or Docker — see CONTAINER; context = repo root)
	@$(call banner,$(CONTAINER) build -f Dockerfile -t medbuddy-api:local .)
	@$(CONTAINER) build -f Dockerfile -t medbuddy-api:local .

##@ Backend — cleanup

be-clean: ## Remove Python caches under backend (keeps .venv)
	@$(call banner,cleaning backend caches)
	@find $(BACKEND) \( -path '$(BACKEND)/.venv' \) -prune -o -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@find . \( -path './$(VENV)' -o -path './.git' \) -prune -o -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(BACKEND)/src/**/*.egg-info $(BACKEND)/dist $(BACKEND)/build .pytest_cache .ruff_cache 2>/dev/null || true
	@$(call ok,clean)

be-clean-all: be-clean ## Remove .venv as well
	@$(call banner,removing $(VENV))
	@rm -rf "$(CURDIR)/$(VENV)"
	@$(call ok,removed $(VENV))

##@ Frontend — Expo (React Native, iOS & Android)

fe-install: ## npm install under apps/frontend
	@$(call banner,npm install $(FRONTEND))
	@cd $(FRONTEND) && npm install
	@$(call ok,frontend deps installed)

fe-dev: fe-dev-mock ## Expo dev server — mock data (same as fe-dev-mock)

fe-dev-mock: fe-install ## Expo with EXPO_PUBLIC_USE_MOCK_DATA=true (default)
	@$(call banner,expo start $(DIM)[mock data]$(NO))
	@cd $(FRONTEND) && EXPO_PUBLIC_USE_MOCK_DATA=true npm run start

fe-dev-api: fe-install ## Expo pointing at real API (set EXPO_PUBLIC_API_BASE_URL in apps/frontend/.env if needed)
	@$(call banner,expo start $(DIM)[useMockData=false]$(NO))
	@cd $(FRONTEND) && EXPO_PUBLIC_USE_MOCK_DATA=false npm run start

fe-build: fe-install ## TypeScript check only (`npm run typecheck`; ship builds use Xcode / Android Studio / EAS)
	@$(call banner,npm run typecheck)
	@cd $(FRONTEND) && npm run typecheck
	@$(call ok,typecheck passed)

fe-run-ios: fe-install ## Native dev build → iOS Simulator (requires Xcode)
	@$(call banner,expo run:ios $(DIM)[Simulator]$(NO))
	@cd $(FRONTEND) && npx expo run:ios

fe-run-android: fe-install ## Native dev build → Android Emulator (requires SDK + AVD)
	@$(call banner,expo run:android $(DIM)[Emulator]$(NO))
	@cd $(FRONTEND) && npx expo run:android

fe-lint: fe-install ## ESLint + TypeScript (same as fe-check)
	@$(call banner,frontend ESLint + tsc)
	@cd $(FRONTEND) && npm run check
	@$(call ok,frontend lint passed)

fe-check: fe-lint ## Alias: ESLint + TypeScript

fe-test: ## No Jest/Vitest wired yet; succeeds with a reminder
	@$(call warn,No frontend unit tests yet — add a test runner and npm script, then wire this target)
	@:
