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

## Quickstart (5 min)

Try it against the **bundled sample vault** — no need to set up your own notes yet:

```bash
git clone https://github.com/alsgur9865-sketch/second-brain-engine
cd second-brain-engine
python -m venv .venv && .venv\Scripts\activate    # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
ollama pull bge-m3                                  # one-time embedding model (~2 GB)
```

Point the engine at the sample vault and start it:

```bash
# bash / macOS / Linux
SB_NOTES_PATH=examples/vault uvicorn app.main:app --port 8000
# Windows PowerShell
$env:SB_NOTES_PATH="examples/vault"; uvicorn app.main:app --port 8000
```

In another terminal, search by *meaning* (not keywords):

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how many days to get a refund?", "k": 3}'
```

You'll get the refund-policy note back even though the keywords don't match.
No Ollama? See [Swapping embedding providers](#swapping-embedding-providers) to use OpenAI instead.

## How it works

```
[ Clients (pluggable) ]
  · Hermes skill (first integration) — cleans conversations with an LLM
  · (future) CLI / web dashboard / other bots
            │  HTTP (JSON)
            ▼
[ Engine core: second-brain-engine ]
  /health · /search · /capture · /reindex · /delete
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
│   ├── config.py       # settings (SB_ env vars) — embedding provider, optional API key
│   ├── embeddings.py   # provider abstraction (Ollama / OpenAI)
│   ├── index.py        # Chroma indexing + incremental sync + search + capture/delete
│   └── main.py         # FastAPI routes (/health, /search, /capture, /reindex, /delete)
├── tests/              # chunking / frontmatter / path-safety + BrainIndex tests
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
copy .env.example .env          # optional — defaults work out of the box (cp on macOS/Linux)
uvicorn app.main:app --port 8000
```

All settings have defaults (see `app/config.py`), so it runs out of the box.
To override, copy `.env.example` to `.env` and edit it, or set `SB_`-prefixed environment variables.

## Run — Option B: Docker

```bash
docker compose up -d
```

> ⚠️ For the container to reach Ollama on the host, run Ollama bound externally
> (`OLLAMA_HOST=0.0.0.0`); otherwise the container can't reach `host.docker.internal:11434`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | status, embedding-backend health, indexed document count |
| POST | `/search` | semantic search (see body below) |
| POST | `/capture` | save a cleaned note + index it immediately (conversation → memory) |
| POST | `/reindex` | force re-sync of changed notes |
| POST | `/delete` | `{"path": "inbox/note.md"}` → delete a note file + its index entries |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "onboarding notes", "k": 5, "tag": "meeting", "folder": "notes", "max_distance": 1.0}'
```

`tag`, `folder`, and `max_distance` are optional filters. Interactive API docs
(Swagger UI) are available at `http://localhost:8000/docs`.

### Authentication (optional)

`SB_API_KEY` is empty by default (no auth). If you set it, send it as an
`X-API-Key` header on every route except `/health`.

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

## License

MIT — see [LICENSE](LICENSE).
