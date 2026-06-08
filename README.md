# second-brain-engine

**English** | [한국어](README.ko.md)

![second-brain-engine](assets/hero.png)

A general-purpose **second-brain engine**: an **agent writes to it (via MCP), and a
human reads it as a graph.** It indexes a folder of Markdown notes and exposes a
small HTTP API — store knowledge, recall it by meaning, let it self-organize, and
explore it as an Obsidian-style graph in your browser.

- **Agent memory (MCP)** — `remember` / `recall` tools let Claude Code (or any MCP
  client: Cursor, Cline, Windsurf, …) store and recall working memory. The engine
  is the single owner of notes + index; the MCP server is a thin proxy.
- **Graph view (browser)** — see what the agent remembered and how it connects:
  `[[wiki-links]]`, semantic similarity, node types (concept / insight / procedure),
  and **relation edges** (supports / refutes / expands). Click a node to read it.
- **Semantic search** — meaning, not keywords. Results carry their `[[wiki-link]]`
  neighbors, so you recall a *connected cluster*, not one chunk.
- **Ask (RAG)** — `POST /ask` searches your notes and a local LLM answers **from
  them only**; strict mode replies "not in memory" instead of hallucinating.
- **Auto-cleanup** — detect near-duplicate notes by embedding, merge them (your text
  or a local-LLM summary); broken `[[links]]` are auto-rewired on merge.
- **Pluggable embeddings** — 7 backends (Ollama, LM Studio, llama.cpp, TEI, OpenAI,
  Voyage, Gemini); switch with one env value, index auto-rebuilds per model.
- **Incremental indexing** — only changed notes are re-embedded; clients just write files.

**Stack**: Python · FastAPI · Chroma (embedded vector DB) · local Ollama LLM
(for cleanup, classification, and answers — no extra infra).

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

Now you can:

```bash
# 1) Search by meaning (not keywords)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how many days to get a refund?", "k": 3}'

# 2) Ask a question — the engine answers from your notes only
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "what is the refund window?"}'
```

…and open **http://localhost:8000** in a browser to see the **graph view** —
nodes colored by type, edges for wiki-links / similarity / relations, with a
detail panel and a question box.

> **Using it as agent memory (MCP)?** You don't even need this step — the MCP
> server auto-starts the engine on first use. See [Agent memory (MCP)](#agent-memory-mcp).

No Ollama? See [Swapping embedding providers](#swapping-embedding-providers) to use OpenAI instead.

## How it works

```
[ Clients (pluggable) ]
  · Agent memory (MCP: remember/recall, cleanup_*)   ← primary, dogfooded with Claude Code
  · Humans (graph view in the browser)               ← same brain, different window
  · (optional) HTTP-direct clients / bots / CLI
            │  MCP (stdio) → HTTP   /   HTTP (JSON)
            ▼
[ Engine core: second-brain-engine ]
  /health · /search · /ask · /capture · /graph · / (graph UI) · /note
  /cleanup/candidates · /cleanup/merge · /classify · /classify-relations
            │
   ┌────────┼──────────────────────┬────────────────────────┐
notes folder (.md)          Chroma vector DB           local LLM (Ollama gemma)
read / write                embeddings + graph         merge · classify · answer
```

The engine is client-agnostic — it only speaks HTTP/JSON. The primary client is
**agent memory over MCP** (dogfooded with Claude Code), and **humans read the same
brain as a graph** in the browser. Anything that speaks HTTP can use it too.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/health` | status, embedding-backend health, indexed document count |
| GET  | `/` | graph view (single-page browser UI) |
| GET  | `/graph` | nodes + edges (wiki-link · semantic-similar · relation) |
| GET  | `/note?path=` | one note's body + metadata (powers the detail panel) |
| POST | `/search` | semantic search (+ `linked` wiki-link neighbors) |
| POST | `/ask` | RAG: search notes → local LLM answers **from them only** (strict) |
| POST | `/capture` | save a cleaned note + index it immediately |
| POST | `/delete` | `{"path": "inbox/note.md"}` → delete a note + its index entries |
| POST | `/reindex` | force re-sync of changed notes |
| GET  | `/cleanup/candidates` | near-duplicate note pairs (embedding similarity) |
| POST | `/cleanup/merge` | merge duplicates (your text, or local-LLM summary) + rewire `[[links]]` |
| POST | `/classify` | tag notes by type — concept / insight / procedure (node color) |
| POST | `/classify-relations` | label similar pairs — supports / refutes / expands (relation edges) |

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "onboarding notes", "k": 5, "tag": "meeting", "folder": "notes", "max_distance": 1.0}'
```

`tag`, `folder`, and `max_distance` are optional filters. With `include_links: true`
(the default), each result also carries `linked` — the notes it points to via
`[[wiki links]]`. Interactive API docs (Swagger UI) are at `http://localhost:8000/docs`.

### Authentication (optional)

`SB_API_KEY` is empty by default (no auth). If you set it, send it as an `X-API-Key`
header on every route except read-only ones (`/health`, `/graph`, `/note`, `/cleanup/candidates`).

## Agent memory (MCP)

The first-class client is an MCP server (`mcp_server.py`, stdio) that proxies the
engine's HTTP API, so an agent like Claude Code can keep its own working memory:

| MCP tool | Engine call | Use |
|---|---|---|
| `remember` | `POST /capture` | save a fact / decision / TODO learned in conversation |
| `recall` | `POST /search` | recall by meaning (+ linked neighbors) |
| `cleanup_candidates` | `GET /cleanup/candidates` | find duplicate memories before merging |
| `cleanup_merge` | `POST /cleanup/merge` | merge duplicates into one note |

Register it with `.mcp.json` or `claude mcp add`, and set your note path in `.env`
(copy from `.env.example`). **You don't need to start the engine yourself** — the MCP
server auto-starts it on the first `remember` / `recall` and keeps it running
(detached), so later sessions connect instantly. The agent writes; you watch the
result in the graph.

## Graph view

Open **http://localhost:8000** while the engine is running:

- **Nodes** are notes, colored by type (concept / insight / procedure; gray = unclassified)
- **Edges**: green = `[[wiki-link]]`, gray = semantic similarity, red = cleanup
  candidate (duplicate), and **labeled relation edges** — teal *supports*, orange
  *refutes*, purple *expands* (run `POST /classify-relations` to populate them)
- **Click a node** to open a detail panel (title · type · tags · body · linked notes);
  click a linked chip or an `/ask` source to jump to that node
- **Question box** (bottom-left) runs `/ask` against your brain

## Run with Docker

```bash
docker compose up -d
```

> ⚠️ For the container to reach Ollama on the host, run Ollama bound externally
> (`OLLAMA_HOST=0.0.0.0`); otherwise it can't reach `host.docker.internal:11434`.

## Swapping embedding providers

The engine needs **one** embedding backend to turn text into vectors — that is what
makes meaning-based search work, so it can't be turned off. But it does **not** have to
be Ollama. Switch with a single env value (plus an API key for cloud providers), then
restart.

| provider | kind | default model | API key | local install |
|---|---|---|---|---|
| `ollama` (default) | local | `bge-m3` | — | required |
| `lmstudio` | local (OpenAI-compatible) | set yourself | — | required |
| `llamacpp` | local (OpenAI-compatible) | set yourself | — | required |
| `tei` | local (OpenAI-compatible) | set yourself | — | required |
| `openai` | **cloud** | `text-embedding-3-small` | ✅ `sk-…` | **none** |
| `voyage` | **cloud** | `voyage-3.5` | ✅ `pa-…` | **none** |
| `gemini` | **cloud** | `gemini-embedding-001` | ✅ `AIza…` | **none** |

### Don't want Ollama? Run fully on the cloud

If you'd rather not install Ollama or any local model, point the engine at a cloud
provider — **no local download, just an API key.** Set two values in `.env` (or the
`env` block of your `.mcp.json`):

```bash
# OpenAI
SB_EMBEDDING_PROVIDER=openai
SB_EMBED_API_KEY=sk-...

# Voyage (Anthropic's recommended partner — Anthropic has no embedding API of its own)
SB_EMBEDDING_PROVIDER=voyage
SB_EMBED_API_KEY=pa-...

# Google Gemini
SB_EMBEDDING_PROVIDER=gemini
SB_EMBED_API_KEY=AIza...
```

Then restart the engine. Optionally set `SB_EMBED_MODEL` to override the default model.

**Trade-off:** with a cloud provider your note text is sent to that API on every
index/search — you give up the "fully local / private" property and you pay per use.
Local providers (Ollama, LM Studio, …) keep everything on your machine.

### How a switch takes effect

Settings are read **once at engine start**, so a change is not live — there is no
slash command or hot-swap. Apply it like this:

1. Edit `SB_EMBEDDING_PROVIDER` (+ `SB_EMBED_API_KEY` for cloud) in `.env` / `.mcp.json`.
2. Restart the engine — stop the process; with MCP auto-start it relaunches on the next
   `remember` / `recall`.
3. On the first search the engine **re-embeds your notes** into a new collection.

Changing the model changes vector dimensions, but the index is **kept per model**
(`second_brain__<provider>_<model>`) — the engine builds the new one on first use and
keeps the old one, so **switching back to a model you used before is instant** (no
re-index).

### Local, but not Ollama

OpenAI-compatible local servers (LM Studio, llama.cpp, TEI) share one client; the
provider name just selects a base-URL preset. Set the model you loaded yourself:

```bash
SB_EMBEDDING_PROVIDER=lmstudio
SB_EMBED_MODEL=text-embedding-bge-m3   # whatever you loaded in LM Studio
# SB_EMBED_BASE_URL=...                # only if your server isn't on the preset port
```

### Generative LLM (separate from embeddings)

The generative LLM is used **only** for `/ask`, auto-cleanup summaries, and node
classification — never for storing or searching. It is currently **Ollama only**
(`gemma4:e4b` by default); you can change the model or URL via `SB_LLM_MODEL` /
`SB_LLM_BASE_URL`, but a cloud LLM provider isn't supported yet. So if you run
embeddings on the cloud and don't want Ollama at all, those three features simply stay
off — notes still **save, search, and graph** fine; nodes just remain unclassified (gray),
and cleanup merges need you to pass the merged text yourself.

## Layout

```
second-brain-engine/
├── app/
│   ├── config.py        # settings (SB_ env vars) — embedding/LLM provider, optional API key
│   ├── embeddings.py    # embedding provider presets (Ollama + OpenAI-compatible)
│   ├── llm.py           # generative LLM (cleanup summary · node type · relation · ask)
│   ├── cleanup.py       # near-duplicate detection (embedding, no LLM)
│   ├── index.py         # Chroma indexing + incremental sync + search + capture/delete + relink
│   ├── graph.py         # nodes/edges (wiki-link · similarity · relation)
│   ├── main.py          # FastAPI routes
│   └── static/graph.html# browser graph view (force-graph, single page)
├── mcp_server.py        # MCP server (remember/recall/cleanup_*) → engine HTTP proxy
├── examples/vault/      # bundled sample notes for the quickstart
├── tests/               # pure functions + BrainIndex (fake embedder) + cleanup/relink/classify
├── Dockerfile · docker-compose.yml · requirements.txt
```

## Development

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## License

MIT — see [LICENSE](LICENSE).
