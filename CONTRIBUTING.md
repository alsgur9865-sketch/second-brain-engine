# Contributing

Thanks for your interest! This is a small, single-maintainer project — issues and
pull requests are welcome.

## Dev setup

```bash
python -m venv .venv && .venv\Scripts\activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Before you open a PR

Both checks must pass:

```bash
ruff check .
pytest
```

- Keep changes focused and match the existing style.
- Pure-function tests live in `tests/` and run without network/DB. `BrainIndex`
  is tested with a fake embedder (see `tests/test_index.py`) — no Ollama needed.
- For any API or behavior change, update **both** `README.md` and `README.ko.md`.

## Project layout

- `app/` — engine core (FastAPI + Chroma). A client-agnostic HTTP API.
- `examples/vault/` — sample notes so anyone can try search immediately.
- `hermes-skill/` — the first client integration (a Discord bot skill).

## Reporting bugs

Open an issue with: what you ran, what you expected, and what actually happened
(logs and the failing request body help a lot).
