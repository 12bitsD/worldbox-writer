PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= python3
PNPM_VERSION ?= 9.15.9
MODEL_EVAL_PROVIDERS ?= all

.PHONY: help setup setup-backend setup-frontend fmt lint lint-backend lint-frontend typecheck test test-backend test-frontend check integration model-eval perf dev-api dev-web clean-reports

help:
	@printf '%s\n' \
		'Available targets:' \
		'  setup            Install backend and frontend dependencies' \
		'  fmt              Format Python code with black and isort' \
		'  lint             Run backend and frontend lint checks' \
		'  typecheck        Run backend mypy checks' \
		'  test             Run backend L1 tests and frontend tests/build' \
		'  check            Run lint + typecheck + test' \
		'  integration      Run pytest integration tests locally' \
		'  model-eval       Run the Sprint 9 multi-model evaluation flow' \
		'  perf             Run the Sprint 9 capacity gate' \
		'  dev-api          Start the FastAPI server' \
		'  dev-web          Start the Vite dev server'

setup: setup-backend setup-frontend

setup-backend:
	PYTHON_BIN=$(BOOTSTRAP_PYTHON) ./scripts/dev/bootstrap-backend.sh

setup-frontend:
	CI=true PNPM_VERSION=$(PNPM_VERSION) ./scripts/dev/bootstrap-frontend.sh

fmt:
	$(PYTHON) -m black .
	$(PYTHON) -m isort .

lint: lint-backend lint-frontend

lint-backend:
	REPORTS_DIR=artifacts/reports/backend PYTHON_BIN=$(PYTHON) ./scripts/ci/backend-quality.sh --lint-only

lint-frontend:
	REPORTS_DIR=artifacts/reports/frontend PNPM_VERSION=$(PNPM_VERSION) ./scripts/ci/frontend-quality.sh --lint-only

typecheck:
	REPORTS_DIR=artifacts/reports/backend PYTHON_BIN=$(PYTHON) ./scripts/ci/backend-quality.sh --typecheck-only

test: test-backend test-frontend

test-backend:
	REPORTS_DIR=artifacts/reports/backend PYTHON_BIN=$(PYTHON) ./scripts/ci/backend-quality.sh --test-only

test-frontend:
	REPORTS_DIR=artifacts/reports/frontend PNPM_VERSION=$(PNPM_VERSION) ./scripts/ci/frontend-quality.sh --test-only

check:
	REPORTS_DIR=artifacts/reports/backend PYTHON_BIN=$(PYTHON) ./scripts/ci/backend-quality.sh
	REPORTS_DIR=artifacts/reports/frontend PNPM_VERSION=$(PNPM_VERSION) ./scripts/ci/frontend-quality.sh

integration:
	$(PYTHON) -m pytest -m integration -v

model-eval:
	MODEL_EVAL_PROVIDERS=$(MODEL_EVAL_PROVIDERS) PYTHON_BIN=$(PYTHON) ./scripts/ci/model-eval.sh

perf:
	PYTHON_BIN=$(PYTHON) ./scripts/ci/perf-gate.sh

dev-api:
	$(PYTHON) -m uvicorn worldbox_writer.api.server:app --host 0.0.0.0 --port 8000

dev-web:
	cd frontend && pnpm dev

clean-reports:
	rm -rf artifacts/reports
