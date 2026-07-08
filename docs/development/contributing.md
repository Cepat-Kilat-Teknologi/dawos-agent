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
pytest tests/ -x -q              # Run 820 tests
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
- **Pylint**: must be 10.00/10
- **Ruff**: zero violations
- **Coverage**: 100%
