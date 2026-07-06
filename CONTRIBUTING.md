# Contributing to dawos-agent

Thank you for your interest in contributing to **dawos-agent**! This guide will help you get started with the development process and ensure your contributions meet our quality standards.

## Table of Contents

- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Code Style Guide](#code-style-guide)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Architecture Notes](#architecture-notes)

## Reporting Bugs

Before filing a bug report, please search existing issues to avoid duplicates.

When reporting a bug, include:

- **Python version** and **OS** (e.g., Python 3.11, Ubuntu 22.04)
- **dawos-agent version** (`pip show dawos-agent`)
- **Steps to reproduce** the issue
- **Expected behavior** vs. **actual behavior**
- **Relevant logs** (sanitize any sensitive data such as API keys)

## Suggesting Features

Feature requests are welcome. Please open an issue describing:

- The problem you are trying to solve
- Your proposed solution
- Any alternatives you have considered

## Development Setup

### Prerequisites

- Python 3.9 or later
- Git

### Steps

1. **Fork and clone** the repository:

   ```bash
   git clone https://github.com/<your-fork>/dawos-agent.git
   cd dawos-agent
   ```

2. **Create a virtual environment**:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install in development mode** with dev dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

4. **Run the test suite**:

   ```bash
   python -m pytest tests/ -x -q
   ```

5. **Run coverage** (target: **100%**):

   ```bash
   coverage run -m pytest tests/ && coverage report -m
   ```

6. **Run linters**:

   ```bash
   black .
   pylint dawos_agent/
   ```

## Code Style Guide

| Rule | Detail |
|------|--------|
| Formatter | **Black** (default settings) |
| Linter | **Pylint** — score must remain **10.00/10** |
| Type hints | Required on all function signatures |
| Docstrings | Required on all public functions, classes, and modules (Google style) |
| Comments | English only |

### Example

```python
def get_session_by_id(session_id: str) -> SessionDetail:
    """Retrieve a single accel-ppp session by its identifier.

    Args:
        session_id: The unique session identifier.

    Returns:
        A SessionDetail model containing the full session state.

    Raises:
        HTTPException: If the session is not found (404).
    """
```

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code change that neither fixes a bug nor adds a feature |
| `test:` | Adding or updating tests |
| `chore:` | Maintenance (CI, deps, tooling) |

Additional rules:

- **Squash commits** before pushing to keep history clean.
- **Never force-push** to `main`.

## Pull Request Process

1. **Branch from `main`** — use a descriptive branch name (e.g., `feat/dhcp-relay-support`).
2. **All tests must pass** — 808+ tests, zero failures.
3. **Coverage must stay at 100%** — add tests for every new code path.
4. **Pylint score must remain 10.00/10** — no exceptions.
5. **Black formatting** — run `black .` before committing.
6. **At least one reviewer approval** is required before merge.
7. Fill in the PR description with a summary of changes and any relevant context.

## Architecture Notes

dawos-agent follows a layered **Router → Service → Shell** pattern:

```
HTTP Request
    │
    ▼
┌─────────┐     ┌───────────┐     ┌───────────┐
│  Router  │────▶│  Service   │────▶│   Shell   │
│ (FastAPI)│     │ (business) │     │(subprocess)│
└─────────┘     └───────────┘     └───────────┘
    │
    ▼
HTTP Response
```

### Key patterns

- **Routers** are organized as `APIRouter(prefix="/api/v1/xxx", tags=["xxx"])`.
- **Services** expose async methods. Each service uses an internal `_run(cmd, sudo=bool)` helper that executes a subprocess and returns `(stdout, returncode)`.
- **Authentication** is via the `X-API-Key` header. Invalid or missing keys return **401 Unauthorized** (not 403).
- **Request/response models** use Pydantic v2.

### Adding a new module

1. Create a service in `dawos_agent/services/` with `_run()` for shell calls.
2. Create a router in `dawos_agent/routers/` with appropriate prefix and tags.
3. Register the router in the application factory.
4. Add comprehensive tests in `tests/` — maintain 100% coverage.

---

Thank you for contributing to dawos-agent!
