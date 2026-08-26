# Cyber Copilot

An AI-powered security investigation platform built on top of **Wazuh**. It
polls Wazuh alerts, opens investigations based on configurable policies, and
hands each one to an autonomous AI agent that gathers its own context,
records everything it does, and produces a verdict — all surfaced through a
web dashboard.

> **Status: work in progress.** The pipeline (poll → policy → investigate →
> review) works end to end, but this is still an early build — see
> [Current Status & Known Limitations](#current-status--known-limitations)
> before relying on it for anything real.

## How it works

```
Wazuh Indexer (OpenSearch)
        │
        ▼
  poller_service.py  ──polls alerts on an interval──┐
        │                                            │
        ▼                                            │
investigation_policy.py  (which alerts matter?)      │
        │                                            │
        ▼                                            │
investigation_manager.py  (open an investigation,    │
                            link/auto-create an asset)│
        │                                            │
        ▼                                            │
  ai_investigator/  ──agentic tool-calling loop──►  LLM (local or API)
        │
        ├── records every tool call → investigation_actions
        ├── records useful findings → investigation_evidence
        └── records the final verdict → investigation_analysis
        │
        ▼
   FastAPI (api/)  ◄────────►  Vue 3 dashboard (frontend/)
```

Alerts can also land in an investigation manually or via the "Start
Investigation" button on an existing one — the AI Investigator doesn't care
how it got triggered, it only needs an alert and an investigation ID.

## The AI Investigator

This is the core of the project (`ai_investigator/`). Given a triggering
Wazuh alert, it runs an **agentic loop**: the LLM looks at the alert,
decides what else it needs to know, calls a tool, reads the result, and
repeats — up to a step/size budget — until it reaches a verdict.

**Tools available to the AI** (`ai_investigator/tools/`):

| Tool | Source | Purpose |
|---|---|---|
| `search_alerts` | Wazuh Indexer | find related alerts by agent, IP, rule, time range, free text |
| `get_alert_details` | Wazuh Indexer | full detail on one specific alert |
| `search_investigations` | MySQL | find related/past investigations |
| `get_investigation` | MySQL | full detail on one investigation |
| `get_investigation_evidence` | MySQL | evidence collected on an investigation |
| `get_investigation_analysis` | MySQL | past AI analyses on an investigation |
| `search_assets` | MySQL | look up a host/endpoint by hostname, IP, or agent ID |
| `get_asset` | MySQL | full detail on one asset |

**By design, the AI has no access to `users` or any user-identifying data**
(no `assigned_to`, `created_by`, `performed_by` lookups) — every tool query
was written to exclude it.

**Every tool call is recorded** in `investigation_actions`, along with the
AI's own reasoning for making that call (what it understood at that point,
not just which tool/arguments) so a human can audit *why* it acted, not
just what it did. Useful findings go to `investigation_evidence`. The final
verdict, confidence, and explanation go to `investigation_analysis`.

**Provider-agnostic by design** (`ai_investigator/llm/`): the loop talks to
an abstract `LLMProvider` interface, not a specific vendor. `APIProvider`
works with any OpenAI-compatible `/chat/completions` endpoint (OpenAI, Groq,
Together, etc.); `LocalProvider` is the same thing pointed at a local Ollama
instance by default. Switching is one `.env` variable
(`LLM_PROVIDER=local|api`) — no code changes.

**Guardrails built into the loop** (`ai_investigator/investigator.py`):

- `MAX_STEPS` — hard cap on tool-calling iterations.
- `MAX_TOOL_RESULT_CHARS` / `MAX_CONVERSATION_CHARS` — bound how much of
  each tool result, and the total conversation, gets resent to the LLM each
  turn (chat completions are stateless, so this compounds over a long
  loop) — once the budget would be exceeded, the loop stops calling tools
  and forces a final verdict with whatever it has.
- An empty final answer (some models return blank `content` after spending
  their token budget on internal reasoning) is treated as a failure, not a
  silently-stored blank analysis.
- Network calls to both the LLM API and the Wazuh Indexer have explicit
  timeouts, and MySQL connections have connect/read/write timeouts — no
  single stuck call can block an investigation forever.
- Rate limiting (`429`) is retried with backoff, but a server-requested
  wait beyond `MAX_RETRY_WAIT_SECONDS` fails fast instead of blocking a
  background job for however long the server asked (this can otherwise
  masquerade as a hang if a provider quota is exhausted).
- Every investigation runs inside a top-level `try/except` — any failure
  (LLM error, tool error, DB error) still gets recorded as an `ERROR`
  verdict and the investigation is always marked `COMPLETED`, so nothing
  is left stuck at `IN_PROGRESS` indefinitely.

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy + PyMySQL, `opensearch-py`
- **Database**: MySQL (investigation data), Wazuh Indexer / OpenSearch (alerts)
- **Frontend**: Vue 3 (Composition API in views, Options API store), Pinia, Vue Router, Tailwind CSS, Vite
- **AI**: any OpenAI-compatible chat-completions API (tested against Groq) or a local Ollama model

## Project structure

```
alert_receiver.py          Wazuh Indexer client (search/get alerts)
poller_service.py          Background polling loop, watermark tracking
investigation_policy.py    PolicyEngine — which alerts open an investigation
investigation_manager.py   Opens investigations, auto-creates/links assets
database.py                MySQL schema (DDL + migrations) + query helpers
logging_config.py          Console + rotating file logging (logs/app.log)

ai_investigator/
  investigator.py          The agentic loop
  llm/                     Provider-agnostic LLM interface (api/local)
  tools/                   Wazuh + database tools available to the AI

api/
  main.py                  FastAPI app, lifespan, routers
  dependencies.py          Service wiring (DB, poller, AI investigator, LLM config)
  routers/                 investigations, policies, assets, users, system(poller)

frontend/
  src/views/               Dashboard, Investigations (list/detail), Assets, Policies, Settings
  src/stores/               Pinia store(s) — investigation state + polling
  src/api/                 Thin fetch wrapper + per-resource API modules
```

## Data model (MySQL)

| Table | Purpose |
|---|---|
| `users` | Analysts — assignment/attribution only, **never exposed to the AI** |
| `assets` | Hosts/endpoints, auto-discovered from Wazuh agents or manually managed |
| `investigation_policies` | Rules deciding which alerts open an investigation |
| `investigations` | One row per investigation — status, severity, linked alert/asset |
| `investigation_evidence` | Findings collected during investigation (by the AI or manually) |
| `investigation_analysis` | Verdict + confidence + explanation (AI or manual) |
| `investigation_actions` | Every tool call the AI made, with its reasoning and result |
| `poller_state` | Poller config + watermark/stats, one row per named poller |

Tables and migrations are created automatically on backend startup
(`Database.init_tables()`).

## Setup

### Prerequisites

- Python 3.10+
- MySQL 8+ (running, reachable)
- A Wazuh Indexer (OpenSearch) to pull alerts from
- Node.js 18+ (for the frontend)
- Either a local [Ollama](https://ollama.com) install, or an API key for
  an OpenAI-compatible provider (Groq, OpenAI, etc.)

### Backend

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env — Wazuh Indexer creds, MySQL creds, LLM provider settings

uvicorn api.main:app --reload
```

The API comes up on `http://localhost:8000` (docs at `/docs`). MySQL tables
are created automatically on first startup.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Comes up on `http://localhost:3000` and proxies `/api/*` to
`http://localhost:8000/*` (see `frontend/vite.config.js` if your backend
runs somewhere else).

### Configuration reference (`.env`)

| Variable | Purpose |
|---|---|
| `WAZUH_INDEXER_HOST/PORT/USERNAME/PASSWORD/VERIFY_SSL` | Wazuh Indexer connection |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | Application database |
| `LLM_PROVIDER` | `local` (Ollama) or `api` (any OpenAI-compatible endpoint) |
| `LLM_BASE_URL` | e.g. `http://localhost:11434/v1` or `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | Model name — must support tool/function calling |
| `LLM_API_KEY` | Required when `LLM_PROVIDER=api` |
| `LLM_TEMPERATURE` | Default `0.1` |
| `LLM_MAX_TOKENS` | Default `4096` — output cap; too low can truncate the model's final answer |

### Starting the pipeline

Once both are running: `POST /api/poller/start` (or use the Settings page)
to begin polling Wazuh alerts, or manually trigger an investigation from
the Investigations page. Each new investigation created by the poller is
handed to the AI Investigator automatically; existing ones can be
(re-)run with the "Start Investigation" button on the investigation's
detail page.

## Current Status & Known Limitations

**Working end to end:**
- Polling → policy evaluation → investigation creation → asset linking
- The AI Investigator's full agentic loop, both from the poller and from
  the frontend's "Start Investigation" button, with live status polling
- Evidence / analysis / actions / timeline views, verdict display
- Delete investigation (cleans up its evidence/analysis/actions first)

**Known gaps, not yet built:**
- **No authentication** — the `users` table exists for
  assignment/attribution, but there's no login flow or session/auth guard.
- **No way to cancel a running investigation** — once started, it runs to
  completion, error, or backend restart.
- Investigation quality varies with the LLM in use — smaller/cheaper
  models can loop somewhat indecisively before converging on a verdict;
  worth tuning `SYSTEM_PROMPT` in `investigator.py` if you see this.
- **Deliberately deferred** (per project scope): Suricata, CloudTrail,
  threat-intel enrichment, and RAG are not integrated. The tool
  architecture is meant to make adding them additive later — new `Tool`
  subclasses, not a redesign.

## Testing changes

There's no automated test suite yet. After backend changes:
```bash
python3 -c "import ast; ast.parse(open('path/to/file.py').read())"  # quick syntax check
```
After frontend changes:
```bash
cd frontend && npm run build
```
