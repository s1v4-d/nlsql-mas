# Makefile for Retail Insights Assistant

NAME := retail_insights
SRC_DIR := src/$(NAME)
TESTS_DIR := tests
UV := uv
PORT ?= 8000
UI_PORT ?= 8501
PID_FILE := .server.pid

# Check if running on Windows
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
    RM := del /F /Q
    RMDIR := rmdir /S /Q
    FIND_PYCACHE := for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
    FIND_PYC := del /S /Q *.pyc 2>nul
else
    VENV_BIN := .venv/bin
    RM := rm -f
    RMDIR := rm -rf
    FIND_PYCACHE := find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    FIND_PYC := find . -type f -name "*.pyc" -delete 2>/dev/null || true
endif

# Default goal
.DEFAULT_GOAL := help

# Phony targets (not actual files)
.PHONY: help install install-dev install-all sync lint lint-fix format \
        test test-unit test-integration test-cov typecheck check \
        clean clean-build clean-pyc clean-cache clean-all \
        start stop dev run-api run-ui docker-build docker-up docker-down \
        pre-commit

help:  ## Display this help message
	@echo.
	@echo Retail Insights Assistant - Development Tasks
	@echo ==============================================
	@echo.
	@echo Usage: make [target]
	@echo.
	@echo Installation:
	@echo   install        Install production dependencies
	@echo   install-dev    Install development dependencies
	@echo   install-all    Install all dependencies (dev + ui + notebooks)
	@echo   sync           Sync dependencies from lock file
	@echo.
	@echo Code Quality:
	@echo   lint           Run linter (ruff check)
	@echo   lint-fix       Run linter with auto-fix
	@echo   format         Format code with ruff
	@echo   typecheck      Run type checker (mypy)
	@echo   check          Run all checks (lint + typecheck)
	@echo.
	@echo Testing:
	@echo   test           Run all tests
	@echo   test-unit      Run unit tests only
	@echo   test-integration  Run integration tests only
	@echo   test-cov       Run tests with coverage report
	@echo.
	@echo Cleanup:
	@echo   clean          Remove cache and temporary files
	@echo   clean-all      Remove all generated files including .venv
	@echo.
	@echo Development:
	@echo   run-api        Start FastAPI development server
	@echo   run-ui         Start Streamlit UI
	@echo   pre-commit     Run pre-commit hooks
	@echo.
	@echo Docker:
	@echo   docker-build   Build Docker images
	@echo   docker-up      Start services with Docker Compose
	@echo   docker-down    Stop Docker Compose services
	@echo.

install:  ## Install production dependencies
	$(UV) sync --no-dev

install-dev:  ## Install development dependencies
	$(UV) sync --extra dev

install-all:  ## Install all dependencies (dev + ui + notebooks)
	$(UV) sync --extra all

sync:  ## Sync dependencies from lock file
	$(UV) sync

lint:  ## Run linter (ruff check)
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR)

lint-fix:  ## Run linter with auto-fix
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --fix

format:  ## Format code with ruff
	$(UV) run ruff format $(SRC_DIR) $(TESTS_DIR)
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --fix

typecheck:  ## Run type checker (mypy)
	$(UV) run mypy $(SRC_DIR) --ignore-missing-imports

check: lint typecheck  ## Run all checks (lint + typecheck)
	@echo All checks passed!

test:  ## Run all tests
	$(UV) run pytest $(TESTS_DIR) -v

test-unit:  ## Run unit tests only
	$(UV) run pytest $(TESTS_DIR)/unit -v

test-integration:  ## Run integration tests only
	$(UV) run pytest $(TESTS_DIR)/integration -v

test-e2e:  ## Run end-to-end tests only
	$(UV) run pytest $(TESTS_DIR)/e2e -v

test-cov:  ## Run tests with coverage report
	$(UV) run pytest $(TESTS_DIR) -v --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

clean-pyc:  ## Remove Python file artifacts
ifeq ($(OS),Windows_NT)
	@$(FIND_PYC)
	@$(FIND_PYCACHE)
else
	$(FIND_PYC)
	$(FIND_PYCACHE)
endif

clean-cache:  ## Remove cache directories
ifeq ($(OS),Windows_NT)
	@if exist .pytest_cache $(RMDIR) .pytest_cache
	@if exist .ruff_cache $(RMDIR) .ruff_cache
	@if exist .mypy_cache $(RMDIR) .mypy_cache
	@if exist .coverage $(RM) .coverage
	@if exist htmlcov $(RMDIR) htmlcov
else
	$(RMDIR) .pytest_cache .ruff_cache .mypy_cache htmlcov 2>/dev/null || true
	$(RM) .coverage 2>/dev/null || true
endif

clean-build:  ## Remove build artifacts
ifeq ($(OS),Windows_NT)
	@if exist build $(RMDIR) build
	@if exist dist $(RMDIR) dist
	@if exist *.egg-info $(RMDIR) *.egg-info
else
	$(RMDIR) build dist *.egg-info 2>/dev/null || true
endif

clean: clean-pyc clean-cache  ## Remove cache and temporary files
	@echo Cleanup complete!

clean-all: clean clean-build  ## Remove all generated files including .venv
ifeq ($(OS),Windows_NT)
	@if exist .venv $(RMDIR) .venv
else
	$(RMDIR) .venv
endif
	@echo Full cleanup complete!

start:  ## Start API and UI servers (background)
ifeq ($(OS),Windows_NT)
	@powershell -Command "Start-Process -FilePath 'uv' -ArgumentList 'run uvicorn retail_insights.api.app:create_app --factory --port $(PORT)' -WindowStyle Hidden"
	@echo API server started on port $(PORT)
else
	@$(UV) run uvicorn retail_insights.api.app:create_app --factory --port $(PORT) & echo $$! > $(PID_FILE)
	@echo "API server started on port $(PORT) (PID: $$(cat $(PID_FILE)))"
endif

stop:  ## Stop background servers
ifeq ($(OS),Windows_NT)
	@powershell -Command "Get-Process -Name 'uvicorn' -ErrorAction SilentlyContinue | Stop-Process -Force"
	@powershell -Command "Get-Process -Name 'streamlit' -ErrorAction SilentlyContinue | Stop-Process -Force"
	@echo Servers stopped
else
	@if [ -f $(PID_FILE) ]; then kill $$(cat $(PID_FILE)) 2>/dev/null || true; rm -f $(PID_FILE); fi
	@pkill -f 'uvicorn.*retail_insights' 2>/dev/null || true
	@pkill -f 'streamlit.*retail_insights' 2>/dev/null || true
	@echo Servers stopped
endif

dev:  ## Run API in development mode (foreground with hot-reload)
	$(UV) run uvicorn retail_insights.api.app:create_app --factory --reload --host 0.0.0.0 --port $(PORT)

run-api:  ## Start FastAPI development server
	$(UV) run uvicorn retail_insights.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

run-ui:  ## Start Streamlit UI
	$(UV) run streamlit run src/retail_insights/ui/app.py

pre-commit:  ## Run pre-commit hooks on all files
	$(UV) run pre-commit run --all-files

docker-build:  ## Build Docker images
	docker compose build

docker-up:  ## Start services with Docker Compose
	docker compose up -d

docker-down:  ## Stop Docker Compose services
	docker compose down

docker-logs:  ## Show Docker Compose logs
	docker compose logs -f

ci-lint:  ## CI: Run linting (exit on error)
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --output-format=github

ci-test:  ## CI: Run tests with JUnit output
	$(UV) run pytest $(TESTS_DIR) -v --junitxml=junit.xml --cov=$(SRC_DIR) --cov-report=xml

all: install-dev lint test  ## Install, lint, and test
	@echo All tasks completed successfully!

qa: format lint typecheck test  ## Run full QA suite (format, lint, typecheck, test)
	@echo QA suite completed!
