# Contributing to dawos-agent

Thank you for your interest in contributing to **dawos-agent**! This guide will help you get started with the development process and ensure your contributions meet our quality standards.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Code Style Guide](#code-style-guide)
- [Testing](#testing)
- [Quality Gates](#quality-gates)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [CI Pipeline](#ci-pipeline)
- [Architecture Notes](#architecture-notes)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior via GitHub Issues.

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
- (Optional) [pre-commit](https://pre-commit.com/) for automatic quality checks

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

3. **Install in development mode** with all dependencies:

   ```bash
   pip install -e ".[dev]"
   pip install pylint black
   ```

4. **Install pre-commit hooks** (recommended):

   ```bash
   pip install pre-commit
   pre-commit install
   ```

5. **Run the test suite** to verify your setup:

   ```bash
   pytest tests/ -x -q
   ```

6. **Run all quality checks**:

   ```bash
   black --check dawos_agent/ tests/
   ruff check dawos_agent/ tests/
   pylint dawos_agent/
   coverage run -m pytest tests/ && coverage report -m
   ```

## Pre-commit Hooks

The project includes a `.pre-commit-config.yaml` that runs three hooks automatically on every `git commit`:

| Hook | What it does |
|------|-------------|
| **Black** | Formats Python code (rev 24.10.0) |
| **Ruff** | Lints and auto-fixes (rev v0.8.6, rules: E/F/W/I/N/UP/B/SIM) |
| **Pylint** | Static analysis on `dawos_agent/` (must score 10.00/10) |

```bash
# Install hooks (one-time)
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Skip hooks in emergencies (not recommended)
git commit --no-verify
```

If a hook fails, fix the issue and re-stage the file before committing again.

## Code Style Guide

### Formatting and Linting

| Tool | Purpose | Configuration |
|------|---------|---------------|
| **[Black](https://black.readthedocs.io/)** | Code formatter (line length 88) | `pyproject.toml` `[tool.black]` |
| **[Ruff](https://docs.astral.sh/ruff/)** | Fast linter (E/F/W/I/N/UP/B/SIM rules) | `pyproject.toml` `[tool.ruff]` |
| **[Pylint](https://pylint.readthedocs.io/)** | Static analysis (10.00/10 required) | `pyproject.toml` `[tool.pylint]` |

### Code Conventions

| Rule | Detail |
|------|--------|
| Type hints | Required on all function signatures |
| Docstrings | Required on all public functions, classes, and modules (Google style) |
| Comments | English only |
| Imports | `from __future__ import annotations` at top of every module |
| No `eval()`/`exec()` | Forbidden anywhere in the codebase |
| No `shell=True` | Always use list-form subprocess arguments |

### Example

```python
from __future__ import annotations

async def get_session_by_id(session_id: str) -> SessionDetail:
    """Retrieve a single accel-ppp session by its identifier.

    Args:
        session_id: The unique session identifier.

    Returns:
        A SessionDetail model containing the full session state.

    Raises:
        HTTPException: If the session is not found (404).
    """
```

## Testing

All tests must pass before submitting a pull request. The minimum coverage requirement is **90%**.

### Running Tests

```bash
# Quick test run (stop on first failure)
pytest tests/ -x -q

# Full coverage report
coverage run -m pytest tests/
coverage report -m

# Generate HTML coverage report
coverage html
open htmlcov/index.html
```

### Test Patterns

- **Mirror source structure** -- each service module gets `test_xxx_service.py`, each router gets `test_xxx.py`
- **Mock at shell level** -- mock `asyncio.create_subprocess_exec` or service functions, not system binaries
- **Async tests** -- use `pytest-asyncio` with `asyncio_mode="auto"` (configured in `pyproject.toml`)
- **Edge cases** -- test error paths, empty data, subprocess failures, and permission errors

### Writing New Tests

When adding a new endpoint or service:

1. Create the test file following the naming convention
2. Mock subprocess calls (never call real system binaries in tests)
3. Test both success and failure paths
4. Verify that coverage stays above 90%:

   ```bash
   coverage run -m pytest tests/ && coverage report -m --fail-under=90
   ```

## Quality Gates

Every pull request must pass all quality gates. These are enforced by the CI pipeline.

| Gate | Target | Command |
|------|--------|---------|
| Tests | 1410 passing | `pytest tests/ -x -q` |
| Coverage | minimum 90% | `coverage report -m` |
| Pylint | 10.00/10 | `pylint dawos_agent/` |
| Black | All formatted | `black --check dawos_agent/ tests/` |
| Ruff | Zero violations | `ruff check dawos_agent/ tests/` |
| Vulnerabilities | 0 known | `pip-audit` |

**Never submit code that drops any of these metrics.**

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
- Commit messages in **English**.

## Pull Request Process

1. **Branch from `main`** -- use a descriptive branch name (e.g., `feat/dhcp-relay-support`).
2. **All quality gates must pass** -- see [Quality Gates](#quality-gates).
3. **Coverage must stay above 90%** -- add tests for new code paths.
4. **Pylint score must remain 10.00/10** -- no exceptions.
5. **Black + Ruff clean** -- run `black dawos_agent/ tests/` and `ruff check dawos_agent/ tests/` before committing.
6. **Pre-commit hooks pass** -- run `pre-commit run --all-files` to verify.
7. **At least one reviewer approval** is required before merge.
8. Fill in the PR description with a summary of changes and any relevant context.

## CI Pipeline

The project uses **GitHub Actions** for continuous integration. Every push and pull request to `main` triggers:

### Lint Job

Runs on Python 3.12:
- Black format check (with `--target-version py39`)
- Ruff lint check
- Pylint analysis (must score 10.00/10)

### Test Job

Runs on a **matrix of Python versions**: 3.9, 3.10, 3.11, 3.12, 3.13

- Full test suite via `coverage run -m pytest`
- Coverage report generation
- Coverage artifact upload (Python 3.12)

### Release Workflow

Triggered on version tags (`v*`):
- Builds sdist + wheel
- Publishes to [PyPI](https://pypi.org/project/dawos-agent/)
- Creates a GitHub Release with the tag

### Docs Workflow

Triggered on changes to `docs/` or `mkdocs.yml`:
- Deploys MkDocs Material site to [GitHub Pages](https://cepat-kilat-teknologi.github.io/dawos-agent/)

## Architecture Notes

dawos-agent follows a layered **Router -> Service -> Shell** pattern:

```
HTTP Request
    |
    v
+---------+     +-----------+     +-----------+
|  Router  |---->|  Service   |---->|   Shell   |
| (FastAPI)|     | (business) |     |(subprocess)|
+---------+     +-----------+     +-----------+
    |
    v
HTTP Response
```

### Key Patterns

- **Routers** are organized as `APIRouter(prefix="/api/v1/xxx", tags=["xxx"])`.
- **Services** expose async methods. Each service uses an internal `_run(cmd, sudo=bool)` helper that executes a subprocess and returns `(stdout, returncode)`.
- **Authentication** is via the `X-API-Key` header. Invalid or missing keys return **401 Unauthorized** (not 403).
- **Request/response models** use Pydantic v2 and are defined in `dawos_agent/models/schemas.py`.

### Adding a New Module

1. Add Pydantic models to `dawos_agent/models/schemas.py`.
2. Create a service in `dawos_agent/services/` with `_run()` for shell calls.
3. Create a router in `dawos_agent/routers/` with appropriate prefix and tags.
4. Mount the router in `dawos_agent/app.py`.
5. Add comprehensive tests in `tests/`.
6. Run all quality gates:

   ```bash
   black dawos_agent/ tests/ && ruff check dawos_agent/ tests/ && pylint dawos_agent/ && pytest tests/ -x -q
   ```

---

Thank you for contributing to dawos-agent!
