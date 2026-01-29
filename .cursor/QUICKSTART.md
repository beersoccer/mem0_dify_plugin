# Quick Start

> For detailed rules and explanations, see `.cursorrules`

## Setup (Choose One)

### Option A: uv (Recommended)
```bash
uv venv
source .venv/bin/activate
uv sync
```

### Option B: conda
```bash
conda create -n dify python=3.12
conda activate dify
pip install -r requirements.txt -r requirements-dev.txt
```

### Option C: venv + pip
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Quick Check (Before Commit)

```bash
# With uv
uv run ruff check . && uv run ruff format --check . && uv run pytest -q

# Without uv
ruff check . && ruff format --check . && pytest -q
```

## Auto-fix Lint Issues

```bash
# With uv
uv run ruff check . --fix
uv run ruff format .

# Without uv
ruff check . --fix
ruff format .
```

## Common Tasks

| Task | Command |
|------|---------|
| Run tests | `pytest -q` or `uv run pytest -q` |
| Lint check | `ruff check .` or `uv run ruff check .` |
| Format check | `ruff format --check .` or `uv run ruff format --check .` |
| Format code | `ruff format .` or `uv run ruff format .` |
| Package plugin | `./build_package.sh` |

## Critical: Runtime Invariants

⚠️ **DO NOT BREAK**:
- `main.py` must set telemetry env vars BEFORE importing mem0
- Graceful shutdown handlers (atexit, SIGTERM, KeyboardInterrupt) must remain

---

**See `.cursorrules` for complete rules and best practices**

