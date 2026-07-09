# Contributing

See [CONTRIBUTING.md](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/CONTRIBUTING.md) for the full guide.

## Quick Setup

```bash
git clone https://github.com/Cepat-Kilat-Teknologi/dawos-agent.git
cd dawos-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install pylint black
```

## Development Commands

```bash
pytest tests/ -x -q              # Run tests
coverage run -m pytest tests/    # Run with coverage
coverage report -m               # Coverage report
pylint dawos_agent/              # Lint (must be 10.00/10)
black --check dawos_agent/ tests/ # Format check
ruff check dawos_agent/ tests/   # Ruff lint
```

## Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

Hooks run Black, Ruff, and Pylint automatically on `git commit`.

## Quality Standards

- **Black**: line-length 88, target py39
- **Pylint**: must score 10.00/10
- **Ruff**: zero violations
- **Coverage**: 100%
- **pip-audit**: zero known vulnerabilities

## Adding a New Endpoint

1. Add Pydantic models to `dawos_agent/models/schemas.py`
2. Create service module in `dawos_agent/services/`
3. Create router in `dawos_agent/routers/` with proper prefix and tags
4. Mount router in `dawos_agent/app.py`
5. Write tests in `tests/` (must maintain 100% coverage)
6. Run all quality checks:

```bash
black dawos_agent/ tests/ && ruff check dawos_agent/ tests/ && pylint dawos_agent/ && pytest tests/ -x -q
```

## Code Style

- **Language**: all code, comments, docstrings, and commits in English
- **Docstrings**: Google-style on all public functions and classes
- **Type hints**: required on all function signatures
- **Imports**: `from __future__ import annotations` at the top of every module

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` -- new feature
- `fix:` -- bug fix
- `docs:` -- documentation only
- `refactor:` -- code change that neither fixes a bug nor adds a feature
- `test:` -- adding or correcting tests
- `chore:` -- maintenance tasks
