# Vilasat AI Support Intelligence — Backend (Phase 10)

FastAPI backend for the support platform: conversations, escalation
tickets, feedback, documents, validation, error handling, migrations,
**embeddings + semantic retrieval (PostgreSQL + pgvector)**, the
**grounded agent core (retrieval → LLM → citation validation)**, and the
**agent decision layer** (ambiguity, evidence sufficiency, conflict,
input safety, escalation offers) — with tests.

**Scope:** Phase 10 keeps the Phase 8B decision layer frozen and connects
the staff workspace to the real ticket API: server-side queue search and
counts, stored ticket detail/transcripts, and atomic status updates with
optimistic concurrency. Phase 9 made the customer chat durable and
duplicate-safe: stable request ids replay completed turns, assistant
replies + citations commit atomically, and a history endpoint restores
transcripts, feedback, and the active ticket. Phase 8B wraps the Phase 8A
grounded pipeline in a typed
decision state machine behind the (additively extended) chat contract:

    input safety (deterministic, 0 LLM calls) → guard
      → question assessment (LLM call #1)  → clarifying question
      → retrieval (approved scope)         → unsupported (empty)
      → relevance gate (deterministic)     → uncertain/weak_relevance
      → coverage gate (deterministic)      → uncertain/partial_coverage
      → evidence verdict (LLM call #2)     → conflict | uncertain
      → generation (LLM call #3, 8A rules) → uncertain/model_declined
      → support check (LLM call #4)        → uncertain/not supported
                                           → grounded

THE LLM HELPS UNDERSTAND LANGUAGE. THE KNOWLEDGE BASE PROVIDES
EVIDENCE. THE APPLICATION CONTROLS THE WORKFLOW — deterministic gates
run first and can only make decisions MORE conservative; ERROR is a
typed HTTP envelope (503/502), never a 200 reply; unsupported ≠
uncertain are never conflated; the LLM never touches tickets. There is
deliberately **no LangChain/LangGraph** (see `docs/PHASE8B_REPORT.md`
§E for the evaluation). The customer frontend now consumes this API
through `src/lib/api/chat-turn.ts`; the Phase 3 mock agent is gone.

## Architecture

```text
Next.js Frontend  ──HTTP/JSON──►  FastAPI routes (app/api)
                                        │  validation + status codes
                                        ▼
                                  Services (app/services)
                        │ chat turns        │ agent core        │ retrieval
                        │ + persistence     │ (agent_service)   │ scope + cosine
                        ▼                   ▼                   ▼
                  Repositories      Evidence context      Embeddings (app/embeddings)
                        │           (E1..En, limits)      │ provider abstraction
                        ▼                   │             │ (nvidia | fake)
                  SQLAlchemy models ◄───────┼─────────────┘
                        │                   ▼
                        │             LLM (app/llm) — provider abstraction
                        │             (nvidia OpenAI-compatible | deterministic stub)
                        ▼
                  PostgreSQL 16 + pgvector (dev + tests, no Docker)
```

| Layer | Responsibility |
| --- | --- |
| `app/api` | HTTP contract: paths, Pydantic validation, status codes |
| `app/schemas` | Request/response shapes (camelCase, matching the frontend contracts); `agent.py` holds the strict internal LLM output schemas (generation + assessment + evidence/support verdicts) |
| `app/services` | Business rules + `agent_service` (decision orchestrator: guard → small-talk screen → assessment → gates → generation → support) + `evidence_assessment` (deterministic gates + verdict parsing) + `conversation_context` (bounded context + working query) + `indexing_service` + `retrieval_service` + `evidence_context` (E1..En builder) |
| `app/llm` | LLM provider boundary: trusted prompt rendering for the FOUR narrow tasks + `complete()` — real (OpenAI-compatible HTTP) + deterministic task-aware stub |
| `app/embeddings` | Provider boundary: `embed_text` / `embed_batch` — real (OpenAI-compatible HTTP) + deterministic test fake |
| `app/repositories` | Reads/writes only — no business logic |
| `app/models` | The tables (Alembic-managed), incl. the native `vector(4096)` embedding column (no HNSW index — above pgvector's 2000-dim cap) |
| `app/core` | Config, logging, the single error envelope |
| `app/db` | Engine/session wiring + idempotent dev seed |
| `scripts/` | `dev_db.py` (embedded Postgres), `index_knowledge.py` (explicit indexing), `update_knowledge.py` (re-ingest changed knowledge files), `probe_embedding_models.py` (live model evaluation), `smoke.py` |

## Requirements

- Python 3.12 (the `pgserver` wheel — bundled PostgreSQL 16.2 + pgvector —
  ships `cp312` binaries for Windows; 3.9–3.12 are supported upstream)
- **No Docker / no system Postgres needed**: development and tests run an
  embedded cluster straight from the Python environment

## Setup

```powershell
# from backend/
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# configuration (placeholders only — no secrets)
Copy-Item .env.example .env    # add EMBEDDING_API_KEY + NVIDIA_API_KEY for real providers

# 1. start the local PostgreSQL + pgvector cluster (fixed port 54329, first run initializes)
.venv\Scripts\python.exe scripts\dev_db.py start

# 2. create tables
.venv\Scripts\alembic.exe upgrade head

# 3. run (auto-ingests knowledge/*.md through the real pipeline when not in production)
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000

# 4. OPTIONAL — embed the corpus (explicit step; requires EMBEDDING_API_KEY)
.venv\Scripts\python.exe scripts\index_knowledge.py            # incremental
.venv\Scripts\python.exe scripts\index_knowledge.py --dry-run  # counts only
.venv\Scripts\python.exe scripts\index_knowledge.py --force    # re-embed everything
```

- API: `http://127.0.0.1:8000` · interactive docs: `/docs` (non-production) · health: `/health`
- The frontend reads `NEXT_PUBLIC_API_BASE_URL` (see the root `.env.example`).
- **Indexing is CLI-only**: never runs at startup, never during a search.
  Without `EMBEDDING_API_KEY` it exits `1` with a clear message instead of
  writing fake vectors (fake provider is refused unless `ENVIRONMENT=testing`).
- Stop the database with `scripts\dev_db.py stop` (`status` to inspect).

## Tests & smoke check

```powershell
# from backend/
.venv\Scripts\python.exe -m pytest            # 373 tests (isolated pgserver test cluster)
.venv\Scripts\python.exe scripts\smoke.py     # live server required (provider-mode dependent)
```

Tests start their **own** embedded PostgreSQL cluster (`backend/data/pg-test`,
dropped/recreated per session) and run on the deterministic fake embedding
provider — no API key, no network. Live-provider smoke is conditional on
credentials and documented as skipped when absent.

## Configuration (`.env.example`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` disables `/docs` and the dev seed; `testing` is the only mode that may use `EMBEDDING_PROVIDER=fake` |
| `DATABASE_URL` | `postgresql+psycopg://postgres@127.0.0.1:54329/vilasat` | Must be `postgresql…` (Phase 7 validator rejects SQLite) |
| `CORS_ORIGINS` | `http://localhost:3000,…` | Comma-separated explicit origins; wildcards are rejected at startup |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `EMBEDDING_PROVIDER` | `nvidia` | `nvidia` = real endpoint; `fake` = test-only |
| `EMBEDDING_MODEL` | `nvidia/nemotron-3.5-embed-8b` | Model id sent to the API **and stored on every vector**. History (probed live, `scripts/probe_embedding_models.py`): `nv-embedqa-e5-v5` EOL (410); `nemotron-3-embed-1b` served but its cosine band was nearly flat (~0.04 margin between on-topic and unrelated pairs) — replaced for retrieval quality |
| `EMBEDDING_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Any OpenAI-compatible endpoint (swap to a self-hosted NIM later) |
| `EMBEDDING_API_KEY` | *(empty)* | Bearer token; never committed, never logged; absence blocks indexing + retrieval with an explicit 503/exit 1 |
| `EMBEDDING_QUERY_INPUT_TYPE` / `EMBEDDING_PASSAGE_INPUT_TYPE` | `query` / `passage` | `input_type` request parameter for ASYMMETRIC models — queries and passages are embedded with their role. Unset (empty) for symmetric models, which never receive the parameter |
| `EMBEDDING_QUERY_PREFIX` / `EMBEDDING_PASSAGE_PREFIX` | `""` | Text role prefixes for E5-family models; the current model takes `input_type` instead and needs none |
| `EMBEDDING_DIMENSIONS` | `4096` | Must equal the `vector(4096)` schema column; mismatches refuse to run |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Per embeddings request |
| `EMBEDDING_BATCH_SIZE` | `1` | Chunks per embedding request — the live endpoint 500s on multi-item batches for the 3.5 models (verified 2026-11-10) |
| `RETRIEVAL_TOP_K_DEFAULT` / `RETRIEVAL_TOP_K_MAX` | `5` / `20` | Explicit top-k bounds (no magic numbers) |
| `RETRIEVAL_MAX_QUERY_CHARS` | `2000` | Query length limit (422 beyond it) |
| `RETRIEVAL_MIN_COSINE_SIMILARITY` | `0.0` | No cutoff by default; sufficiency is judged downstream by the gates |
| `LLM_PROVIDER` | `stub` | `stub` = deterministic dev/test generator (refused in `production`); `nvidia` = real chat endpoint |
| `LLM_MODEL` | `nvidia/nemotron-3.5-bolt-e4b` | Chat model id, verified live with the strict-JSON contract and deterministic at temperature 0.0. Known-bad: `deepseek-ai/deepseek-v4.1-flash` (listed by `/models` but inference hangs indefinitely, verified 2026-11-10); `meta/llama-3.3-70b-instruct` (EOL, 410); `nvidia/nemotron-3.5-super-vl-120b-a12b` (reasoning model — non-deterministic at temperature 0) |
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Any OpenAI-compatible chat endpoint |
| `NVIDIA_API_KEY` | *(empty)* | LLM credential; may equal the embedding key but is read independently; never committed, never logged; absence → explicit `503 LLM_PROVIDER_UNAVAILABLE` |
| `LLM_TIMEOUT_SECONDS` | `60` | Per chat-completion request |
| `LLM_TEMPERATURE` | `0.0` | Grounded structured output wants determinism |
| `LLM_MAX_COMPLETION_TOKENS` | `4096` | Endpoint cap is 4096; validated `[1, 4096]`. Keep at the cap for reasoning models (their `reasoning_tokens` consume this budget — a smaller value truncates answers) |
| `LLM_MAX_EVIDENCE` | `10` | Max evidence items sent to the model per turn (matches the agent's retrieval pool) |
| `LLM_EVIDENCE_MAX_CHARS` | `1200` | Per-item evidence text cap (≈ chunk size) — prompts stay bounded |
| `AGENT_RETRIEVAL_TOP_K` | `12` | Candidate pool the agent retrieves per turn — wider than the public retrieval default (5) because ranking alone can miss on-topic chunks; the gates still decide sufficiency |
| `AGENT_MIN_EVIDENCE_RELEVANCE` | `0.05` | Decision signal A: best candidate's cosine must reach this bar. Deliberately permissive — the coverage gate and support check carry the protection. Live 3.5-embed-8b measures ~0.47–0.77 for on-topic queries vs ~0.24–0.39 unrelated |
| `AGENT_MIN_COVERAGE_RATIO` | `0.75` | Decision signal B: fraction of the question's material words covered by the evidence; below → typed `uncertain`, never a guess |
| `AGENT_CONTEXT_MAX_MESSAGES` | `6` | Bounded conversation context: last N messages sent per turn |
| `AGENT_CONTEXT_MAX_CHARS` | `500` | Per-message truncation inside the context window |

## API surface (all under `/api/v1`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/chat/sessions` | Start a conversation |
| POST | `/chat/sessions/{id}/messages` | Send a message → typed reply turn. Optional `clientRequestId` makes the turn idempotent (retries replay the stored turn) |
| GET | `/chat/sessions/{id}/messages` | Read-only transcript: messages, citations, recorded feedback, active ticket — for page reload |
| POST | `/conversations/{id}/escalations` | Create an escalation ticket (409 on duplicate) |
| GET | `/admin/escalations` | Staff queue (`status`, `q` incl. email, `limit`, `offset`) + query-scoped status `counts` |
| GET | `/admin/escalations/{id}` | Ticket detail + stored transcript/citations + events |
| PATCH | `/admin/escalations/{id}/status` | Status change + audit event in one transaction; optional `expectedStatus` returns 409 on a stale write |
| POST | `/messages/{id}/feedback` | `helpful` / `not_helpful` (409 if repeated) |
| GET | `/documents` | Documents + processing status + chunk counts |
| GET | `/documents/{id}` | Detail: stored content + chunks with section provenance |
| POST | `/documents` | Synchronous ingestion: validate → extract → normalize → chunk → `READY` |
| POST | `/documents/{id}/reprocess` | Re-run the pipeline over stored content (replaces chunks) |
| POST | `/retrieval/search` | **Development/internal**: semantic candidates for a query - **no answer field, no sufficiency claim** |
| GET | `/admin/provider-settings` | Provider/status snapshot for the staff dialog (booleans + masked keys, never key material) |
| PUT | `/admin/provider-settings/keys` | Persist submitted NVIDIA keys to `backend/.env` and refresh live settings (staff dialog) |
| POST | `/admin/provider-settings/verify` | One real provider call per submitted key; a wrong key is `ok: false`, not a fake success |
| PUT | `/admin/provider-settings/mode` | Local **Demo/Live** switch (`{"mode":"demo"\|"live"}`). Demo is deterministic, needs no key, and never rewrites live vectors; refused in production |
| GET | `/health` | Liveness + environment + provider `mode` (`offline_demo` / `live` / `partial`) — drives the UI mode banner |

Every failure returns the same envelope:

```json
{ "error": { "code": "…", "message": "…", "details": null, "request_id": "…" } }
```

Stack traces, prompts, keys and database details are never returned —
they go to the server log only. Provider/pipeline failures map to
explicit codes: `503 EMBEDDING_PROVIDER_UNAVAILABLE`, `503
LLM_PROVIDER_UNAVAILABLE` (missing key, transport, truncated/empty
completion — at ANY of the four decision calls), `502 GENERATION_FAILED`
(malformed structured output at any decision stage — assessment,
evidence verdict, generation, support check — or citations that were
not part of this turn's retrieved evidence); invalid payloads to `422`.
An ERROR is never disguised as a decision: the customer gets the typed
envelope, the turn is safe to retry. A failed generation persists the
customer message but no assistant answer, and retrying the identical
message reuses the unanswered row instead of duplicating it.

## Agent decision layer (Phases 8A + 8B)

Chat replies come from the decision state machine in
`app/services/agent_service.py` (`run_agent_turn`), which wraps the 8A
grounded pipeline as its generation stage:

0. **Input safety first** — a curated deterministic pattern screen
   short-circuits injection-style attempts to the typed `guard` reply
   with **zero LLM calls** (works with or without credentials).
   Architecture is the real defense: trusted instructions vs. untrusted
   data, app-validated structured output, no DB/ticket authority for the
   model. The screen is belt-and-braces and deliberately NOT exhaustive —
   a near-miss falls through and is processed as ordinary data.
1. **Question assessment** (LLM call #1, pre-retrieval) — materially
   ambiguous questions get exactly ONE concise clarifying question with
   1–4 options; clarification content is app-validated (no internal ids,
   no secret-ish phrases, single "?"). Malformed → `502`, never repaired.
2. **Retrieval** — Phase 7 semantic search, approved scope only,
   SQL-enforced (challenge fixtures unreachable through chat). Empty →
   typed `unsupported` with zero generation calls.
3. **Deterministic gates** — relevance (signal A: best cosine ≥
   `AGENT_MIN_EVIDENCE_RELEVANCE`) and coverage (signal B: fraction of
   the question's material words present in the evidence ≥
   `AGENT_MIN_COVERAGE_RATIO`). Failures → typed `uncertain` with the
   escalation offer, BEFORE any answer is generated. Gates run first and
   can only make decisions MORE conservative — an LLM verdict never
   resurrects a turn that failed a gate.
4. **Evidence verdict** (LLM call #2, skipped when < 2 items — conflict
   is impossible) — `sufficient` / `insufficient` / `conflicting`. A
   conflict claim needs ≥ 2 DISTINCT refs from THIS turn's evidence;
   single-ref or invented "conflicts" are malformed → `502`.
5. **Generation** (LLM call #3 — the unchanged Phase 8A rules) —
   controlled evidence `E1..En`, trusted/untrusted separation, strict
   structured output, citation validation against this turn's map.
6. **Support check** (LLM call #4, narrow judge) — the candidate answer
   must stay within its evidence; `supported` must equal
   `category == "supported"`. An answer that exceeds its evidence is
   discarded — never persisted, never shown.
7. **Typed outcomes** — `grounded` (validated citations persisted with
   chunk provenance + evidence snapshot), `clarifying`, `guard`,
   `unsupported`, `uncertain` (five internal categories, one typed text:
   weak_relevance / partial_coverage / evidence_insufficient /
   model_declined / answer_not_supported), `conflicting`. Dead ends
   (unsupported / uncertain / conflict) attach a fixed application-
   controlled **escalation offer**; the LLM never chooses wording for a
   non-grounded outcome and never creates tickets — a human hand-off
   stays the existing customer-submitted Phase 5 endpoint.
8. **Demo-mode determinism extras (8b-7)** — two deterministic, 0-LLM-call
   screens keep Demo mode on par with Live: filler greetings ("ok hi")
   classify as small talk through the same typed GREETING_TEXT (screen,
   stub and assessment prompt rule 6), and the working question is
   spelling-corrected against the retrievable corpus vocabulary
   (`app/services/query_correction.py`) — the demo analog of the live
   pipeline's assessment search_query + typo-robust embeddings. The rule
   is conservative: unique near-match only, same first letter, small
   edit budget, short filler tokens never touched.

The conversation context sent to the model is BOUNDED (last
`AGENT_CONTEXT_MAX_MESSAGES` messages, each truncated to
`AGENT_CONTEXT_MAX_CHARS` — the full history never reaches a prompt),
and a follow-up to a clarifying question is retrieved with a composed
working query (triggering message + current message) so turn 2 sees
turn 1's intent.

Honest limitation: citation validation + the support judge prove
references point at this turn's evidence — they do NOT prove factual
correctness of the underlying documents, and the deterministic gates
use lexical/numerical signals that are UNCALIBRATED for live embeddings
(see `.env.example` and `docs/PHASE8B_REPORT.md` §D).

## Data model

`Conversation 1—n Message 1—n Citation (evidence snapshot at answer time)`
`Message 1—1 Feedback`

Phase 9 adds `messages.client_request_id` (one customer submission per
conversation; partial unique index, NULL for legacy rows) and
`messages.reply_to_message_id` (one assistant reply per customer turn;
partial unique index + `ON DELETE SET NULL`).
`Conversation 1—n Ticket 1—n TicketEvent`
`Document 1—n DocumentChunk` (provenance: chunk index + section id/title;
duplicate detection by SHA-256 of normalized content)

`DocumentChunk` embedding columns (native pgvector, never JSON arrays):

| Column | Meaning |
| --- | --- |
| `embedding` | `vector(4096)` — `NULL` = not indexed yet → simply not searchable |
| `embedding_model` | Which model produced it — retrieval filters on the configured model, so old-model vectors are never treated as current |
| `embedding_fingerprint` | Content-derived identity: `sha256(doc.content_hash : chunk_index : sha256(chunk.content))` — never row ids; changed → re-embed on next run |
| `embedded_at` | When the vector was written (explicit run only) |

Indexed by exact sequential cosine scan (no HNSW: pgvector's HNSW caps at
2000 dimensions, below the current model's 4096). `documents.knowledge_status`
classifies every document — `approved` (normal retrieval), `challenge_fixture`
(labeled conflicting-evidence material, reachable only through the service-level
`include_challenge_fixtures` flag — the HTTP schema forbids it), `archived`
(**never** indexed, never retrieved). The scope filter lives **inside the SQL
query**, not in post-processing.

Messages and citations are append-only historical evidence: a stored
reply is never regenerated or overwritten. Reprocessing a document
replaces its chunks but nulls citation chunk links instead of deleting
citations — the evidence snapshot preserves what supported the answer.

## What remains before production

Staff/admin authentication is **not implemented**. `/api/v1/admin/*` is
open on the local development server; this is a production security
blocker. The same applies to the Demo/Live switch (local operator
surface); Demo mode itself is refused when `ENVIRONMENT=production`, so
a deployment cannot serve deterministic demo answers to real traffic. The Phase 10 report records the intended boundary and the
remaining security gates. Also still open are the Phase 8B §K
pre-production validation gates: live provider smoke, a realistic
evaluation set, and live-embedding threshold calibration.
