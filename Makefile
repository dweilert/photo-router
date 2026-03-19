# ---------------------------------------------------------------------------
# photo-router — development task runner
# ---------------------------------------------------------------------------

PYTHON      := python3
PIP         := $(PYTHON) -m pip
APP_DIRS    := app tests
IMAGE_NAME  := photo-router

.PHONY: help install lint format format-check test check build clean

# Default target
help:
	@echo ""
	@echo "  photo-router build targets"
	@echo "  --------------------------"
	@echo "  make install       Install all dev dependencies"
	@echo "  make lint          Run ruff linter (no auto-fix)"
	@echo "  make format        Auto-format code with black + ruff --fix"
	@echo "  make format-check  Check formatting without modifying files (CI)"
	@echo "  make test          Run pytest with coverage"
	@echo "  make check         Full CI gate: lint + format-check + test"
	@echo "  make build         Build Docker image (runs check first)"
	@echo "  make clean         Remove __pycache__ and .coverage artifacts"
	@echo ""

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

# ---------------------------------------------------------------------------
# Lint — ruff only, no auto-fix (informational)
# ---------------------------------------------------------------------------
lint:
	@echo ">>> ruff lint"
	ruff check $(APP_DIRS)

# ---------------------------------------------------------------------------
# Format — auto-fix in place (developer convenience)
# ---------------------------------------------------------------------------
format:
	@echo ">>> black (auto-format)"
	black $(APP_DIRS)
	@echo ">>> ruff --fix (auto-fix imports + upgrades)"
	ruff check --fix $(APP_DIRS)

# ---------------------------------------------------------------------------
# Format-check — fail if code is not already formatted (used by 'check')
# ---------------------------------------------------------------------------
format-check:
	@echo ">>> black --check"
	black --check $(APP_DIRS)
	@echo ">>> ruff check (no fix)"
	ruff check $(APP_DIRS)

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
test:
	@echo ">>> pytest"
	pytest

# ---------------------------------------------------------------------------
# Check — full CI gate (lint + format-check + test, in order)
# ---------------------------------------------------------------------------
check: format-check test
	@echo ""
	@echo "  All checks passed."
	@echo ""

# ---------------------------------------------------------------------------
# Build — only after check passes
# ---------------------------------------------------------------------------
build: check
	@echo ">>> docker build"
	docker build -t $(IMAGE_NAME):latest .

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "coverage.xml" -delete 2>/dev/null || true
	@echo ">>> clean done"
