.PHONY: dev install-dev test test-quick lint format check audit docs docs-serve clean help

PYTHON  ?= python3
VENV    := .venv
PIP     := $(VENV)/bin/pip
PYTEST  := $(VENV)/bin/python -m pytest
BLACK   := $(VENV)/bin/python -m black
PYLINT  := $(VENV)/bin/python -m pylint
RUFF    := $(VENV)/bin/python -m ruff
COV     := $(VENV)/bin/python -m coverage
MKDOCS  := $(VENV)/bin/python -m mkdocs
AUDIT   := $(VENV)/bin/pip-audit

# ----------------------------------------------------------------------
# Development
# ----------------------------------------------------------------------

## Set up development environment (venv + editable install + dev deps)
dev: $(VENV)/bin/activate
	@echo ""
	@echo "Dev environment ready. Activate with: source .venv/bin/activate"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PIP) install pylint black
	@touch $(VENV)/bin/activate

## Install dev deps into existing venv
install-dev:
	$(PIP) install -e ".[dev]"
	$(PIP) install pylint black

# ----------------------------------------------------------------------
# Quality
# ----------------------------------------------------------------------

## Run all tests with coverage
test:
	$(COV) run -m pytest tests/ -x -q
	$(COV) report -m

## Run tests without coverage (faster)
test-quick:
	$(PYTEST) tests/ -x -q

## Run linters (black --check + pylint + ruff)
lint:
	$(BLACK) --check dawos_agent/ tests/
	$(PYLINT) dawos_agent/
	$(RUFF) check dawos_agent/ tests/
	@echo ""
	@echo "All lint checks passed."

## Format code with black
format:
	$(BLACK) dawos_agent/ tests/
	@echo ""
	@echo "Code formatted."

## Run all checks (lint + test) -- CI gate
check: lint test
	@echo ""
	@echo "All checks passed -- ready to commit."

## Audit dependencies for known vulnerabilities
audit:
	$(AUDIT)

# ----------------------------------------------------------------------
# Documentation
# ----------------------------------------------------------------------

## Build MkDocs documentation (strict mode)
docs:
	$(MKDOCS) build --strict
	@echo ""
	@echo "Docs built in site/ directory."

## Serve docs locally for preview
docs-serve:
	$(MKDOCS) serve

# ----------------------------------------------------------------------
# Cleanup
# ----------------------------------------------------------------------

## Remove build artifacts and caches
clean:
	rm -rf build/ dist/ *.egg-info .eggs/
	rm -rf .pytest_cache/ htmlcov/ .coverage
	rm -rf site/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

# ----------------------------------------------------------------------
# Help
# ----------------------------------------------------------------------

## Show this help
help:
	@echo "dawos-agent Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make dev          Set up dev environment (.venv + deps)"
	@echo "  make test         Run tests with coverage report"
	@echo "  make test-quick   Run tests without coverage (faster)"
	@echo "  make lint         Run black --check + pylint + ruff"
	@echo "  make format       Format code with black"
	@echo "  make check        Run all checks (lint + test)"
	@echo "  make audit        Audit dependencies for vulnerabilities"
	@echo "  make docs         Build MkDocs documentation"
	@echo "  make docs-serve   Serve docs locally (http://localhost:8000)"
	@echo "  make clean        Remove build artifacts"
	@echo "  make help         Show this help"
