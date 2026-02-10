# Contributing to Retail Insights Assistant

Thank you for your interest in contributing to this project. This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)

---

## Code of Conduct

This project adheres to professional standards of conduct. Contributors are expected to:

- Be respectful and constructive in all communications
- Focus on technical merit when reviewing contributions
- Accept constructive feedback gracefully
- Report any inappropriate behavior to the maintainers

---

## Getting Started

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Docker and Docker Compose
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/nlsql-mas.git
cd nlsql-mas
```

3. Add the upstream remote:

```bash
git remote add upstream https://github.com/s1v4-d/nlsql-mas.git
```

---

## Development Setup

### Install Dependencies

```bash
# Install all dependencies including development tools
uv sync

# Copy environment configuration
cp env-files/secrets/secrets.env.example env-files/secrets/secrets.env
```

### Start Development Services

```bash
# Start PostgreSQL and Redis
make start

# Verify services are running
docker ps
```

### Run Tests

```bash
# Run the full test suite
make test

# Run with coverage
make test-cov
```

---

## Making Changes

### Branch Naming Convention

Create a branch from `main` using the following naming pattern:

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/description` | `feat/add-cache-layer` |
| Bug Fix | `fix/description` | `fix/executor-timeout` |
| Documentation | `docs/description` | `docs/update-readme` |
| Refactor | `refactor/description` | `refactor/agent-state` |
| Test | `test/description` | `test/validator-edge-cases` |

```bash
git checkout -b feat/your-feature-name
```

### Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Each commit message must follow this format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:**

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style changes (formatting, no logic change) |
| `refactor` | Code refactoring |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |
| `perf` | Performance improvements |

**Scopes:**

| Scope | Description |
|-------|-------------|
| `agents` | LangGraph agent changes |
| `api` | FastAPI route changes |
| `engine` | DuckDB/data layer changes |
| `ui` | Streamlit interface changes |
| `core` | Configuration, logging, utilities |
| `infra` | Terraform/infrastructure changes |
| `deps` | Dependency updates |

**Examples:**

```
feat(agents): add schema discovery with LLM tools
fix(executor): handle DuckDB timeout gracefully
docs(readme): add deployment instructions
test(unit): add validator boundary tests
```

---

## Pull Request Process

### Before Submitting

1. Ensure all tests pass:

```bash
make test
```

2. Run code quality checks:

```bash
make lint
make format
uv run mypy src/
```

3. Update documentation if needed

4. Rebase on latest main:

```bash
git fetch upstream
git rebase upstream/main
```

### Pull Request Template

When opening a PR, include:

- **Summary**: Brief description of changes
- **Motivation**: Why these changes are needed
- **Changes**: List of specific modifications
- **Testing**: How the changes were tested
- **Breaking Changes**: Any backward-incompatible changes

### Review Process

1. All PRs require at least one approving review
2. CI checks must pass (tests, linting, type checking)
3. Address all review comments before merging
4. Squash commits when merging to main

---

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/) conventions
- Use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Maximum line length: 100 characters

### Type Annotations

- All functions must have type annotations
- Use `mypy` for static type checking
- Prefer `|` over `Union` for type unions (Python 3.10+)

```python
def process_query(query: str, timeout: float | None = None) -> QueryResult:
    ...
```

### Pydantic Models

- Use Pydantic v2 for all data models
- Include field descriptions for API models
- Use `Field()` for validation constraints

```python
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000)
    mode: QueryMode = Field(default=QueryMode.QUERY)
```

### Documentation

- Use docstrings for all public functions and classes
- Follow Google docstring format
- Keep comments minimal; prefer self-documenting code

---

## Testing Requirements

### Test Categories

| Category | Marker | Description |
|----------|--------|-------------|
| Unit | `@pytest.mark.unit` | Isolated component tests |
| Integration | `@pytest.mark.integration` | Multi-component tests |
| End-to-End | `@pytest.mark.e2e` | Full workflow tests |

### Coverage Requirements

- Minimum coverage: 80% for new code
- All public functions must have tests
- Edge cases and error conditions must be tested

### Test Structure

```
tests/
├── unit/           # Unit tests (no external dependencies)
├── integration/    # Integration tests (mocked services)
├── e2e/            # End-to-end tests (full stack)
├── fixtures/       # Shared test fixtures and data
└── conftest.py     # Pytest configuration
```

### Running Specific Tests

```bash
# Run unit tests only
uv run pytest -m unit

# Run tests for a specific module
uv run pytest tests/unit/test_validator.py

# Run tests with verbose output
uv run pytest -v

# Run tests matching a pattern
uv run pytest -k "test_route"
```

---

## Questions

If you have questions about contributing, please open a GitHub issue with the `question` label.
