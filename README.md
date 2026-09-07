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
| `check_ip_reputation` | AbuseIPDB (external) | is a source/destination IP known-malicious? Abuse confidence score, report count, ISP, country |

`check_ip_reputation` is a single outbound HTTP request per IP (no local
dataset or ML model, so it stays fast and light) and is cached in-process
for an hour so the same IP isn't looked up twice. Private/internal IPs are
recognized locally and never sent out. It only appears in the tool list at
all when `ABUSEIPDB_API_KEY` is set — with no key, the AI is never offered
a tool it can't use. The same tool set (including this one) is shared with
the [chat assistant](#chat-assistant) described below.

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

## Chat Assistant

A free-form chat UI (`/chat` in the frontend, `ai_investigator/chatbot.py` +
`api/routers/chat.py` on the backend) for asking the AI about alerts,
investigations, or assets directly, outside the fixed investigate-one-alert
flow. It shares the exact same tool set as the AI Investigator (the table
above) via `ai_investigator/tools/build_default_tools` — including the same
hard restriction that nothing can read the `users` table.

Each turn only persists the user's message and the assistant's final
answer; the tool-calling round trip within a turn is rebuilt from that
history and discarded once the turn ends, so conversation size (and LLM
request cost) stays bounded no matter how long a chat session runs.

## Authentication

There's no separate password database for this app. Logging in checks the
username/password you type **against your Wazuh Indexer** — the same
account the Wazuh Dashboard itself uses:

1. `POST /auth/login` sends your credentials to the Wazuh Indexer as HTTP
   Basic Auth on one lightweight request. `200` = valid account, `401` =
   invalid. The password is forwarded for that single check and never
   stored.
2. On success, the backend issues its own short-lived signed **JWT**
   (`AUTH_TOKEN_TTL_MINUTES`, default 12h) — the Indexer has no reusable
   token to hand back, so the app mints one. The frontend sends it as
   `Authorization: Bearer <token>` on every request from then on.
3. The first successful login for a given Wazuh username auto-creates a
   matching row in the app's own `users` table (role `analyst`). That row
   — not anything from Wazuh — is what the app would use for per-feature
   permissions; there's only one access tier today, so every authenticated
   user has full access.

Every route requires a valid token except `/auth/login` and `/health`.

### Finding your Wazuh username/password

This app doesn't create Wazuh accounts — you log in with one that already
exists on your Wazuh Indexer. Where to find it depends on what you still
have from the install:

- **Right after a fresh install**, the Wazuh installer wrote a
  `wazuh-install-files.tar` in whatever directory you ran
  `wazuh-install.sh` from (often `~` or wherever you downloaded it).
  Extract it and read the generated passwords:
  ```bash
  tar -xf wazuh-install-files.tar
  cat wazuh-install-files/wazuh-passwords.txt
  ```
  This lists every internal account (`admin`, `kibanaserver`, `wazuh_wui`,
  etc.) with the password Wazuh generated for it at install time. `admin`
  is the one you want — it's the same login the Wazuh Dashboard uses.

- **If that file is gone** (Wazuh's own docs recommend deleting it after
  saving the passwords elsewhere), the passwords are stored as salted
  hashes on the Indexer and can't be recovered — only reset. Use the
  password tool that ships with the Indexer:
  ```bash
  sudo bash /usr/share/wazuh-indexer/plugins/opensearch-security/tools/wazuh-passwords-tool.sh -h
  ```
  to see the exact flags for your version — typically `-u <username> -p
  <new-password>` to set a specific account's password, or `-a` to
  regenerate random passwords for every internal account and print them.

Don't confuse this with `WAZUH_INDEXER_USERNAME`/`WAZUH_INDEXER_PASSWORD`
in `.env` — that pair is a *service* account this app's own backend uses
to pull alerts (poller, AI Investigator, chat). It's unrelated to what a
human types into the login screen; any valid Indexer account works there,
including that same service account if you don't mind reusing it.

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
  chatbot.py               Free-form multi-turn chat, same tools as the investigator
  llm/                     Provider-agnostic LLM interface (api/local)
  tools/                   Wazuh + database + threat-intel tools available to the AI

api/
  main.py                  FastAPI app, lifespan, routers, route protection
  dependencies.py          Service wiring (DB, poller, AI investigator, LLM config)
  auth.py                  Wazuh-credential login check + JWT issuing/verification
  routers/                 auth, investigations, policies, assets, users, system(poller), chat

frontend/
  src/views/               Dashboard, Investigations (list/detail), Assets, Policies, Settings, Chat, Login
  src/stores/               Pinia store(s) — investigation state + polling, auth/session
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
| `chat_sessions` / `chat_messages` | Chat Assistant conversations and messages |

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
| `LLM_REASONING_EFFORT` | Optional `low`/`medium`/`high` — supported by some models (Groq's gpt-oss family, OpenAI o-series); lowers hidden chain-of-thought token usage per call |
| `ABUSEIPDB_API_KEY` | Optional. Enables the `check_ip_reputation` tool (free tier: 1000 checks/day). Get one at [abuseipdb.com/account/api](https://www.abuseipdb.com/account/api). Leave blank to disable the tool entirely |
| `AUTH_JWT_SECRET` | Signs this app's session tokens — see [Authentication](#authentication). Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`. Changing it logs everyone out |
| `AUTH_TOKEN_TTL_MINUTES` | How long a login stays valid, in minutes. Default `720` (12h) |

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
- Wazuh-credential login, session tokens, route protection (see [Authentication](#authentication))
- Free-form chat with the AI over the same tool set (see [Chat Assistant](#chat-assistant))

**Known gaps, not yet built:**
- **No per-feature permissions** — every logged-in user has full access
  today (see [Authentication](#authentication)); `users.role` exists but
  nothing checks it yet.
- **No way to cancel a running investigation** — once started, it runs to
  completion, error, or backend restart.
- Investigation quality varies with the LLM in use — smaller/cheaper
  models can loop somewhat indecisively before converging on a verdict;
  worth tuning `SYSTEM_PROMPT` in `investigator.py` if you see this.
- **Deliberately deferred** (per project scope): Suricata, CloudTrail, and
  RAG are not integrated. IP reputation (`check_ip_reputation`, via
  AbuseIPDB) is the first threat-intel source; the tool architecture is
  meant to make adding more additive later — new `Tool` subclasses, not a
  redesign.

## Testing changes

There's no automated test suite yet. After backend changes:
```bash
python3 -c "import ast; ast.parse(open('path/to/file.py').read())"  # quick syntax check
```
After frontend changes:
```bash
cd frontend && npm run build
```
