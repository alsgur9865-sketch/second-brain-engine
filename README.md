# second-brain-engine

**English** | [한국어](README.ko.md)

![second-brain-engine](assets/hero.png)

A general-purpose **second-brain engine** that auto-captures conversations and
recalls them via semantic search. It indexes a folder of Markdown notes and
exposes a small HTTP API — any client (a Discord bot, a CLI, a web dashboard, …)
can store and search knowledge over it.

- **Stack**: Python · FastAPI · Chroma (embedded vector DB)
- **Pluggable embeddings**: local Ollama by default, switch to OpenAI (or any provider) with one config value
- **Incremental indexing**: only changed notes are re-embedded; clients just write files
- **Auto-capture**: `POST /capture` persists a cleaned note and indexes it immediately — the "conversation → memory" path

## How it works

```
[ Clients (pluggable) ]
  · Hermes skill (first integration) — cleans conversations with an LLM
  · (future) CLI / web dashboard / other bots
            │  HTTP (JSON)
            ▼
[ Engine core: second-brain-engine ]
  /health · /search · /capture · /reindex
            │
   ┌────────┴───────────────┐
notes folder (.md)      Chroma vector DB
read / write            embedding index
```

The engine is client-agnostic — it only speaks HTTP/JSON. Hermes (a Discord bot)
is currently the first and primary client, but nothing in the engine depends on it.

## Layout

```
second-brain-engine/
├── app/
│   ├── config.py       # settings (SB_ env vars) — embedding provider selection
│   ├── embeddings.py   # provider abstraction (Ollama / OpenAI)
│   ├── index.py        # Chroma indexing + incremental sync + search + capture
│   └── main.py         # FastAPI routes (/health, /search, /reindex, /capture)
├── tests/              # chunking unit tests
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Prerequisites (local Ollama embeddings)

```bash
ollama pull bge-m3        # default model — strong multilingual / Korean
```

## Run — Option A: local Python

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

All settings have defaults (see `app/config.py`), so it runs out of the box.
To override, set `SB_`-prefixed environment variables or create a `.env` file.

## Run — Option B: Docker

```bash
docker compose up -d
```

> ⚠️ For the container to reach Ollama on the host, run Ollama bound externally
> (`OLLAMA_HOST=0.0.0.0`); otherwise the container can't reach `host.docker.internal:11434`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | status + indexed document count |
| POST | `/search` | `{"query": "...", "k": 5}` → semantic search results |
| POST | `/reindex` | force re-sync of changed notes |
| POST | `/capture` | save a cleaned note + index it immediately (conversation → memory) |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "onboarding notes", "k": 5}'
```

## Swapping embedding providers

Change the provider via env. To add a new one, add a class in `app/embeddings.py`
plus one branch in `get_embedder`.

```bash
# switch to OpenAI
SB_EMBEDDING_PROVIDER=openai
SB_OPENAI_API_KEY=sk-...
```

> ⚠️ Changing the provider changes vector dimensions. Delete `chroma_db/` and
> re-index (`POST /reindex`, or remove the folder and restart).

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## Clients & integrations

The engine is general-purpose — any client that speaks HTTP can use it. The first
integration is **Hermes** (a Discord bot): it keeps a separate notes repo
(`my-second-brain`) cloned locally, reads/writes files directly, and calls
`/search` when it needs semantic recall. See `hermes-skill/second-brain/SKILL.md`.
