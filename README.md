# Nexus ERP

Pluggable, bidirectional ERP integration platform with an AI-driven transformation layer. Connect Sage Intacct to Dynamics 365, SAP S/4HANA, NetSuite, Oracle ERP Cloud — or any custom ERP — without rebuilding the core.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Phoenix LiveView UI  (port 4000)                           │
│  Real-time dashboards · Mapping editor · Agent proposals    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (Req)
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI  (port 8000)                                        │
│  Connectors · Pipelines · Schema registry · Mappings        │
│  Agent API · Sync events · Health                           │
└───┬──────────────┬───────────────┬───────────────┬──────────┘
    │              │               │               │
┌───▼───┐    ┌─────▼────┐   ┌─────▼────┐   ┌─────▼────┐
│Celery │    │  Kafka   │   │  NAM     │   │  NNLM    │
│Worker │    │+ Debezium│   │Query+Enc │   │Enc+Dec   │
└───┬───┘    └──────────┘   └──────────┘   └──────────┘
    │
┌───▼──────────────────────────────────────────────────────────┐
│  ERP Connectors (plugin architecture)                        │
│  Sage Intacct · Dynamics 365 · SAP S/4HANA                  │
│  NetSuite · Oracle ERP Cloud · custom plugins                │
└──────────────────────────────────────────────────────────────┘
```

**Stack:**
- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), Celery, APScheduler
- **Frontend**: Elixir/Phoenix LiveView, Tailwind CSS
- **Messaging**: Apache Kafka, Debezium CDC
- **AI layer**: LangGraph, Anthropic Claude, NAM (Neural Addressed Memory), NNLM
- **Storage**: PostgreSQL, Redis
- **Infrastructure**: Docker Compose, Alembic migrations

---

## Features

### Pluggable Connector System
Each ERP connector implements the `ERPConnector` abstract base class. Drop a new connector into `plugins/` and it's auto-discovered at startup — no central registry edits required.

```
backend/connectors/
  sage_intacct/    # XML API + session auth
  dynamics365/     # MSAL OAuth2 + OData
  sap_s4hana/      # Basic auth + OData v4 + CSRF
  netsuite/        # TBA OAuth 1.0 + SuiteTalk REST
  oracle_erp/      # Basic auth + Oracle REST
plugins/           # drop third-party connectors here
```

### Bidirectional Sync
- **Direction**: forward (source → target), reverse (target → source), or both
- **Conflict resolution**: last-write-wins by `updated_at` timestamp; Sage Intacct is the tie-breaker hub
- **Loop prevention**: `ExternalIdMap` table tracks source↔target record IDs and payload hashes — unchanged records are skipped, already-synced records are never re-synced in the opposite direction

### Schema Registry
Every connector's entity schemas are versioned. On each discovery run, a SHA-256 hash comparison detects drift and produces a structured diff `{added, removed, changed}`. Diffs trigger the healing agent automatically.

### AI-Driven Transformation Layer
1. **Schema mapping agent** — queries NNLM for grounded context from previously indexed schemas, then calls Claude to propose field mappings with confidence scores
2. **Code generation** — compiles approved mappings into `transform_forward` / `transform_reverse` Python functions, executed in a RestrictedPython sandbox (no imports allowed)
3. **Self-healing pipelines** — on schema drift, the healing agent retrieves relevant past mappings from NAM via NNLM and proposes updated transformations
4. **Human-in-the-loop** — LangGraph pauses at `human_checkpoint`; proposals are reviewed via the Phoenix UI before any code is applied

### NAM + NNLM Integration
[NAM (Neural Addressed Memory)](../nam-0.0.1) stores schema definitions, approved mappings, and sync events as semantically addressed records using multi-head encoding (ontology, entity, attribute, affordance, context).

[NNLM](../nnlm) sits on top of NAM and provides:
- **Encoder** (port 8001): multi-agent retrieval pipeline — supervisor → entity resolver → NAM query → quality gate
- **Decoder** (port 8002): grounded synthesis with citation tracking — LLM outputs are constrained to indexed facts, preventing hallucination

All agent nodes query NNLM *before* calling Claude, so every mapping proposal and healing suggestion is grounded in real schema data.

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- The `nam-0.0.1` and `nnlm` packages at `../nam-0.0.1` and `../nnlm` relative to this directory (i.e. `~/Development/`)
- An Anthropic API key

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:
```
ANTHROPIC_API_KEY=sk-ant-...
FERNET_KEY=<generate with command in .env.example comment>
```

### 2. Start the stack

```bash
make up
```

This builds and starts all services: Postgres, Redis, Kafka, Debezium, NAM, NNLM, FastAPI, Celery, Phoenix UI.

First startup takes several minutes while Docker builds the NAM and NNLM images.

### 3. Run migrations

```bash
make migrate
```

### 4. Open the UI

[http://localhost:4000](http://localhost:4000)

---

## Development

### Local backend (no Docker for Python services)

```bash
# Start infrastructure only
make dev

# Run migrations
alembic upgrade head

# Start FastAPI
uvicorn backend.main:app --reload

# Start Celery worker
celery -A backend.workers.celery_app worker --loglevel=info -Q sync,agent
```

### Local frontend

```bash
cd ui
mix deps.get
mix phx.server
```

### Available make targets

```
make up        # docker compose up --build (full stack)
make down      # docker compose down
make dev       # start infrastructure only (postgres, redis, kafka)
make migrate   # run alembic migrations
make logs      # follow all service logs
```

---

## Adding a Custom Connector

1. Create a directory under `plugins/your_erp/`
2. Implement `ERPConnector` from `backend.connectors.base`:

```python
from backend.connectors.base import ERPConnector, ConnectorMeta, EntitySchema, SyncRecord

class YourERPConnector(ERPConnector):
    class Meta(ConnectorMeta):
        name = "your_erp"
        display_name = "Your ERP"
        supported_entities = ["Invoice", "Vendor", "Customer"]

    async def connect(self): ...
    async def disconnect(self): ...
    async def list_entities(self) -> list[str]: ...
    async def read_schema(self, entity_name: str) -> EntitySchema: ...
    async def fetch_records(self, entity_name, since, page_size, cursor): ...
    async def push_records(self, entity_name, records): ...
    async def subscribe_to_changes(self, entity_name): ...
```

3. Restart the API — the registry auto-discovers it.

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

| Resource | Endpoints |
|---|---|
| Connectors | `GET/POST /connectors`, `GET/PUT/DELETE /connectors/{id}`, `POST /connectors/{id}/test` |
| Pipelines | `GET/POST /pipelines`, `GET/PUT/DELETE /pipelines/{id}`, `POST /pipelines/{id}/start`, `POST /pipelines/{id}/run` |
| Schemas | `GET /schemas/{connector_id}`, `POST /schemas/{connector_id}/discover` |
| Mappings | `GET/PUT /pipelines/{id}/mappings`, `GET /pipelines/{id}/transformation`, `POST /pipelines/{id}/transformation/test` |
| Agent | `POST /agent/pipelines/{id}/trigger`, `GET /agent/proposals`, `POST /agent/proposals/{id}/review` |
| Sync Events | `GET /sync-events`, `GET /sync-events/stats/summary` |
| Health | `GET /health`, `GET /health/ready` |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Project Structure

```
nexus-erp/
├── backend/
│   ├── agent/              # LangGraph graphs + nodes (mapping, healing)
│   ├── api/v1/             # FastAPI route handlers
│   ├── connectors/         # ERP connector implementations
│   ├── core/               # Config, DB, security, logging
│   ├── db/                 # SQLAlchemy ORM models
│   ├── llm/                # NAM + NNLM clients, schema indexer
│   ├── messaging/          # Kafka producer/consumer
│   ├── pipeline/           # Runner, conflict resolver, poller
│   ├── schema_registry/    # Schema versioning + drift detection
│   ├── transformation/     # Mapping compiler + RestrictedPython sandbox
│   └── workers/            # Celery tasks (sync + agent)
├── ui/                     # Elixir Phoenix LiveView application
├── alembic/                # Database migrations
├── plugins/                # Drop custom connectors here
├── docker-compose.yml
├── Dockerfile.api
└── pyproject.toml
```

---

## License

MIT
