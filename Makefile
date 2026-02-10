# Makefile for Retail Insights Assistant
NAME := retail_insights
SRC_DIR := src/$(NAME)
TESTS_DIR := tests
PORT ?= 8000
COMPOSE_FILE := env-files/docker-compose.yml
SECRETS_FILE := env-files/secrets/secrets.env
SECRETS_EXAMPLE := env-files/secrets/secrets.env.example

# Platform detection
ifeq ($(OS),Windows_NT)
    DETECTED_OS := windows
    VENV_BIN := .venv/Scripts
    RM := del /F /Q
    RMDIR := rmdir /S /Q
    FIND_PYCACHE := for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
    FIND_PYC := del /S /Q *.pyc 2>nul
    COPY := copy
    SHELL_CMD := powershell -NoProfile -Command
    NULL := 2>nul
else
    DETECTED_OS := $(shell uname -s | tr '[:upper:]' '[:lower:]')
    VENV_BIN := .venv/bin
    RM := rm -f
    RMDIR := rm -rf
    FIND_PYCACHE := find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    FIND_PYC := find . -type f -name "*.pyc" -delete 2>/dev/null || true
    COPY := cp
    NULL := 2>/dev/null || true
endif

# Tool detection
HAS_UV := $(shell uv --version $(NULL) && echo 1)
HAS_DOCKER := $(shell docker --version $(NULL) && echo 1)
HAS_TERRAFORM := $(shell terraform --version $(NULL) && echo 1)
UV := uv
COMPOSE := docker compose -f $(COMPOSE_FILE)

.DEFAULT_GOAL := help
.PHONY: help init init-infra build start start-d start-db stop stop-v logs watch dev \
        run-ui lint lint-fix format typecheck check test test-unit test-integration test-cov \
        clean clean-pyc clean-cache ci-lint ci-test qa pre-commit shell-api shell-db ps info install-uv

help:
	@echo ""
	@echo "Retail Insights Assistant"
	@echo "========================="
	@echo ""
	@echo "Setup:"
	@echo "  init         Install dependencies, setup secrets, pre-commit"
	@echo "  init-infra   Initialize Terraform for infrastructure"
	@echo "  info         Show detected environment info"
	@echo ""
	@echo "Docker:"
	@echo "  build        Build all Docker images"
	@echo "  start        Start all services (foreground)"
	@echo "  start-d      Start all services (detached)"
	@echo "  start-db     Start database services only (postgres + redis)"
	@echo "  stop         Stop services and prune images"
	@echo "  stop-v       Stop and remove volumes (destructive)"
	@echo "  watch        Start with hot reload (Docker Compose Watch)"
	@echo "  logs         Follow all service logs"
	@echo "  ps           Show running containers"
	@echo "  shell-api    Open shell in API container"
	@echo "  shell-db     Open psql in database container"
	@echo ""
	@echo "Local Development:"
	@echo "  dev          Run API locally with hot-reload"
	@echo "  run-ui       Run Streamlit UI locally"
	@echo ""
	@echo "Terraform (TF_ENV=dev|staging|prod):"
	@echo "  tf-init      Initialize Terraform backend and providers"
	@echo "  tf-plan      Generate and show execution plan"
	@echo "  tf-apply     Apply the planned changes"
	@echo "  tf-destroy   Destroy all managed infrastructure"
	@echo "  tf-fmt       Format all Terraform files"
	@echo "  tf-validate  Validate Terraform configuration"
	@echo "  tf-lint      Run TFLint on infrastructure"
	@echo "  tf-docs      Generate Terraform documentation"
	@echo ""
	@echo "Quality:"
	@echo "  lint         Run linter"
	@echo "  format       Format code"
	@echo "  typecheck    Run mypy type checker"
	@echo "  test         Run all tests"
	@echo "  qa           Run format, lint, typecheck, test"
	@echo "  pre-commit   Run all pre-commit checks (format, lint, typecheck, test)"
	@echo ""

info:
	@echo "OS: $(DETECTED_OS)"
	@echo "uv: $(if $(HAS_UV),installed,NOT FOUND)"
	@echo "Docker: $(if $(HAS_DOCKER),installed,NOT FOUND)"
	@echo "Terraform: $(if $(HAS_TERRAFORM),installed,NOT FOUND)"

install-uv:
ifndef HAS_UV
ifeq ($(OS),Windows_NT)
	@echo Installing uv...
	@powershell -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
else
	@echo Installing uv...
	@curl -LsSf https://astral.sh/uv/install.sh | sh
endif
else
	@echo uv already installed
endif

check-docker:
ifndef HAS_DOCKER
	$(error Docker not found. Install Docker Desktop from https://docker.com)
endif
	@docker info >$(if $(filter $(OS),Windows_NT),nul,/dev/null) 2>&1 || (echo "Docker daemon not running. Start Docker Desktop." && exit 1)

$(SECRETS_FILE):
ifeq ($(OS),Windows_NT)
	@if not exist "env-files\secrets" mkdir "env-files\secrets"
	@if not exist "$(SECRETS_FILE)" $(COPY) "$(SECRETS_EXAMPLE)" "$(SECRETS_FILE)"
else
	@mkdir -p env-files/secrets
	@test -f "$(SECRETS_FILE)" || $(COPY) "$(SECRETS_EXAMPLE)" "$(SECRETS_FILE)"
endif
	@echo Created $(SECRETS_FILE) from template

init: install-uv $(SECRETS_FILE)
	$(UV) sync --extra all
	@echo ""
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -Command "if (Get-Command pre-commit -ErrorAction SilentlyContinue) { uv run pre-commit install } else { Write-Host 'Run: uv run pre-commit install' }"
else
	@command -v pre-commit >/dev/null 2>&1 && $(UV) run pre-commit install || echo "Run: uv run pre-commit install"
endif
	@echo ""
	@echo "=== Setup Complete ==="
	@echo "1. Edit $(SECRETS_FILE) with your API keys"
	@echo "2. Run 'make dev' for local development (API only)"
	@echo "3. Run 'make build && make start' for full Docker stack"
	@echo ""

init-infra:
ifndef HAS_TERRAFORM
ifeq ($(OS),Windows_NT)
	@echo Terraform not found. Install with: winget install Hashicorp.Terraform
else ifeq ($(DETECTED_OS),darwin)
	@echo Terraform not found. Install with: brew install terraform
else
	@echo Terraform not found. Install from: https://developer.hashicorp.com/terraform/downloads
endif
	@exit 1
endif
	cd infrastructure/environments/dev && terraform init
	@echo "Terraform initialized. Run 'make tf-plan' to see changes."

# Terraform Commands
TF_ENV ?= dev
TF_DIR := infrastructure/environments/$(TF_ENV)

.PHONY: tf-init tf-plan tf-apply tf-destroy tf-fmt tf-validate tf-lint tf-docs

tf-init:
ifndef HAS_TERRAFORM
	@echo "Terraform not found. Run 'make init-infra' for installation instructions."
	@exit 1
endif
	cd $(TF_DIR) && terraform init

tf-plan:
ifndef HAS_TERRAFORM
	@echo "Terraform not found."
	@exit 1
endif
	cd $(TF_DIR) && terraform plan -out=tfplan

tf-apply:
ifndef HAS_TERRAFORM
	@echo "Terraform not found."
	@exit 1
endif
	cd $(TF_DIR) && terraform apply tfplan

tf-destroy:
ifndef HAS_TERRAFORM
	@echo "Terraform not found."
	@exit 1
endif
	cd $(TF_DIR) && terraform destroy

tf-fmt:
	terraform fmt -recursive infrastructure/

tf-validate:
ifndef HAS_TERRAFORM
	@echo "Terraform not found."
	@exit 1
endif
	cd $(TF_DIR) && terraform validate

tf-lint:
	@command -v tflint >/dev/null 2>&1 || { echo "tflint not found. Install with: brew install tflint"; exit 1; }
	tflint --init
	tflint --recursive --config=.tflint.hcl

tf-docs:
	@command -v terraform-docs >/dev/null 2>&1 || { echo "terraform-docs not found. Install with: brew install terraform-docs"; exit 1; }
	terraform-docs markdown table --recursive infrastructure/modules -c .terraform-docs.yml

build: check-docker stop
	$(COMPOSE) build
	@echo ""
	@echo "Build complete. Run 'make start' to launch all services."

start: check-docker
	$(COMPOSE) up

start-d: check-docker
	$(COMPOSE) up -d
	@echo "Services started in background. Run 'make logs' to view output."

start-db: check-docker
	$(COMPOSE) up -d db redis
	@echo "Waiting for database health check..."
ifeq ($(OS),Windows_NT)
	@powershell -NoProfile -Command "Start-Sleep -Seconds 5; docker compose -f $(COMPOSE_FILE) exec db pg_isready -U postgres -d retail_insights"
else
	@sleep 5 && $(COMPOSE) exec db pg_isready -U postgres -d retail_insights || sleep 3
endif
	@echo "Database services ready!"
	@echo "PostgreSQL: localhost:5432"
	@echo "Redis: localhost:6379"

stop:
	-$(COMPOSE) down --remove-orphans 2>$(if $(filter $(OS),Windows_NT),nul,/dev/null)
	-docker image prune -f 2>$(if $(filter $(OS),Windows_NT),nul,/dev/null)

stop-v:
	@echo "WARNING: This will delete all data volumes!"
	$(COMPOSE) down -v --remove-orphans

watch: check-docker
	$(COMPOSE) up --watch

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

ps:
	$(COMPOSE) ps

shell-api: check-docker
	$(COMPOSE) exec api /bin/bash

shell-db: check-docker
	$(COMPOSE) exec db psql -U postgres -d retail_insights

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
	$(RMDIR) .pytest_cache .ruff_cache .mypy_cache htmlcov $(NULL)
	$(RM) .coverage $(NULL)
endif

clean: clean-pyc clean-cache

ci-lint:
	$(UV) run ruff check $(SRC_DIR) $(TESTS_DIR) --output-format=github

ci-test:
	$(UV) run pytest $(TESTS_DIR) -v --junitxml=junit.xml --cov=$(SRC_DIR) --cov-report=xml

pre-commit: format lint typecheck test
