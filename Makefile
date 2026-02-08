# Makefile for Retail Insights Assistant

NAME := retail_insights
SRC_DIR := src/$(NAME)
TESTS_DIR := tests
UV := uv
PORT ?= 8000
COMPOSE_FILE := env-files/docker-compose.yml
SECRETS_FILE := env-files/secrets/secrets.env
SECRETS_EXAMPLE := env-files/secrets/secrets.env.example

ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
    RM := del /F /Q
    RMDIR := rmdir /S /Q
    FIND_PYCACHE := for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
    FIND_PYC := del /S /Q *.pyc 2>nul
    COPY := copy
    FILE_EXISTS = if exist $(1)
else
    VENV_BIN := .venv/bin
    RM := rm -f
    RMDIR := rm -rf
    FIND_PYCACHE := find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    FIND_PYC := find . -type f -name "*.pyc" -delete 2>/dev/null || true
    COPY := cp
    FILE_EXISTS = test -f $(1) &&
endif

.DEFAULT_GOAL := help
.PHONY: help init build start stop logs dev lint format typecheck test clean

help:
	@echo.
	@echo Retail Insights Assistant
	@echo ========================
	@echo.
	@echo   init     Install dependencies and setup secrets
	@echo   build    Build Docker images (stops first)
	@echo   start    Start all services (foreground)
	@echo   stop     Stop services and clean images
	@echo   logs     Show service logs
	@echo   dev      Run API locally with hot-reload
	@echo.
	@echo   lint     Run linter
	@echo   format   Format code
	@echo   test     Run tests
	@echo   clean    Remove cache files
	@echo.

init: $(SECRETS_FILE)
	$(UV) sync --extra all
	@echo.
	@echo Dependencies installed. Edit $(SECRETS_FILE) with your API keys.

$(SECRETS_FILE):
ifeq ($(OS),Windows_NT)
	@if not exist "$(SECRETS_FILE)" $(COPY) "$(SECRETS_EXAMPLE)" "$(SECRETS_FILE)"
else
	@if [ ! -f "$(SECRETS_FILE)" ]; then $(COPY) "$(SECRETS_EXAMPLE)" "$(SECRETS_FILE)"; fi
endif
	@echo Created $(SECRETS_FILE) from template

build: stop
	docker compose -f $(COMPOSE_FILE) build
	@echo.
	@echo Build complete. Run 'make start' to launch.

start:
	docker compose -f $(COMPOSE_FILE) up

stop:
	docker compose -f $(COMPOSE_FILE) down --remove-orphans
	docker image prune -f

logs:
	docker compose -f $(COMPOSE_FILE) logs -f

dev:
	$(UV) run uvicorn retail_insights.api.app:create_app --factory --reload --host 0.0.0.0 --port $(PORT)

run-ui:
	$(UV) run streamlit run src/retail_insights/ui/app.py

lint:
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR)

lint-fix:
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --fix

format:
	$(UV) run ruff format $(SRC_DIR) $(TESTS_DIR)
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --fix

typecheck:
	$(UV) run mypy $(SRC_DIR) --ignore-missing-imports

check: lint typecheck

test:
	$(UV) run pytest $(TESTS_DIR) -v

test-unit:
	$(UV) run pytest $(TESTS_DIR)/unit -v

test-integration:
	$(UV) run pytest $(TESTS_DIR)/integration -v

test-cov:
	$(UV) run pytest $(TESTS_DIR) -v --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

clean-pyc:
ifeq ($(OS),Windows_NT)
	@$(FIND_PYC)
	@$(FIND_PYCACHE)
else
	$(FIND_PYC)
	$(FIND_PYCACHE)
endif

clean-cache:
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

clean: clean-pyc clean-cache

ci-lint:
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --output-format=github

ci-test:
	$(UV) run pytest $(TESTS_DIR) -v --junitxml=junit.xml --cov=$(SRC_DIR) --cov-report=xml

qa: format lint typecheck test
