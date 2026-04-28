# Global Interconnectedness Index (GII)

Composite bilateral index scoring country-pair interconnectedness across three pillars: **trade** (UN Comtrade), **travel** (OpenFlights + UNWTO), and **geopolitics** (GDELT via BigQuery). Orchestrated by Temporal, enriched by LangChain agents, served via FastAPI + HTMX dashboard.

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials (see sections below)
```

### 3. Run database migrations

```bash
uv run alembic upgrade head
```

### 4. Seed country reference data

```bash
uv run python scripts/seed_countries.py
```

### 5. Start Temporal dev server (separate terminal)

```bash
temporal server start-dev
```

This starts the Temporal server on `localhost:7233` with a web UI at `localhost:8080`. The server is just the orchestrator — it doesn't run your code.

### 6. Start the Temporal worker (separate terminal)

```bash
uv run python -m gii.pipelines.worker
```

The **worker** is the process that actually executes activities (API calls, BigQuery queries, index computation, LangChain agents). All credentials in `.env` need to be accessible to this process.

### 7. Start the web app

```bash
uv run gii
```

- Dashboard: http://localhost:8000
- API docs: http://localhost:8000/docs
- Temporal UI: http://localhost:8080

---

## GCP / GDELT Authentication

The GDELT pipeline queries BigQuery, which requires GCP credentials. Three auth paths are supported, in priority order:

### Option 1: Service account JSON file via `.env` (recommended for local dev)

Set `GII_GCP_CREDENTIALS_PATH` in your `.env` to the absolute path of a service account JSON file:

```
GII_GCP_PROJECT_ID=my-project-123
GII_GCP_CREDENTIALS_PATH=/Users/you/keys/service-account.json
```

The worker process reads this path at runtime. The service account needs the **BigQuery Data Viewer** and **BigQuery Job User** roles.

### Option 2: `GOOGLE_APPLICATION_CREDENTIALS` env var

If you don't set `GII_GCP_CREDENTIALS_PATH`, the Google Cloud client library falls back to the standard `GOOGLE_APPLICATION_CREDENTIALS` env var. You can set this in `.env`:

```
GOOGLE_APPLICATION_CREDENTIALS=/Users/you/keys/service-account.json
```

Or export it in your shell before starting the worker:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/Users/you/keys/service-account.json"
uv run python -m gii.pipelines.worker
```

> **Note**: Set this on the **worker** process, not on `temporal server start-dev`. The Temporal server doesn't need GCP credentials — it just schedules work. The worker is what runs BigQuery queries.

### Option 3: Application Default Credentials (GCP-hosted or gcloud CLI)

If neither of the above is set, the client uses [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials):

- **On GCP** (Cloud Run, GCE, GKE): automatically uses the attached service account. No config needed.
- **Local dev with gcloud**: run `gcloud auth application-default login` once, then the worker picks up your user credentials.

---

## LLM Provider Configuration

The quality-check and narrative agents require an LLM. Two providers are supported, controlled by `GII_LLM_PROVIDER`:

### NVIDIA NIM (default)

```bash
GII_LLM_PROVIDER=nvidia
GII_NVIDIA_API_KEY=nvapi-...
GII_LLM_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5
```

Get an API key at https://build.nvidia.com. The integration automatically retries on 429/502/503 with exponential backoff (up to 5 attempts).

### AWS Bedrock

```bash
GII_LLM_PROVIDER=bedrock
GII_BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0
GII_BEDROCK_REGION=us-east-1
```

Bedrock uses the standard AWS credential chain — no API key needed in `.env`. Ensure your environment has credentials via one of:

- `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars
- `~/.aws/credentials` profile
- IAM role (ECS task role, EC2 instance profile, etc.)

The IAM principal needs the `bedrock:InvokeModel` permission for the configured model.

### Switching providers

Both providers expose the same interface (`bind_tools`, streaming, structured output). To switch, change `GII_LLM_PROVIDER` and restart the worker and web app. No code changes needed.

---

## Temporal Workflows

### Architecture

```
MainRefreshWorkflow (top-level orchestrator)
  ├── TradeDataWorkflow (child)     → fetch_and_store_trade activity
  ├── TravelDataWorkflow (child)    → fetch_and_store_flights + ingest_and_store_unwto activities
  ├── GeopoliticsDataWorkflow (child) → fetch_and_store_gdelt activity
  ├── run_quality_check activity    (LangChain DataQualityAgent)
  ├── compute_and_store_index activity
  └── generate_narratives activity  (LangChain NarrativeAgent)
```

The three data-source child workflows run **in parallel**. Once all three complete, the pipeline runs quality checks, computes the composite index, and generates AI narratives — sequentially.

### Running Workflows

There are four ways to trigger workflows:

#### 1. Dashboard UI

Navigate to http://localhost:8000/admin/pipelines, enter the period (e.g. `2024`), and click **Trigger Refresh**.

#### 2. API endpoint

```bash
curl -X POST http://localhost:8000/api/pipelines/trigger \
  -H "Content-Type: application/json" \
  -d '{"period": "2024"}'
```

#### 3. Backfill script (one-time historical load)

```bash
# Default: backfill period 2024
uv run python scripts/run_backfill.py

# Specific period
uv run python scripts/run_backfill.py 2023
```

This blocks until the full pipeline completes and prints the results.

#### 4. Temporal CLI (direct workflow control)

> **Note:** The Temporal CLI sends input directly to the internal `PipelineParams` dataclass which requires both `year` (int) and `period` (string). The HTTP API only requires `period` and derives the year automatically.

```bash
# Start a workflow
temporal workflow start \
  --task-queue gii-pipeline \
  --type MainRefreshWorkflow \
  --input '{"year": 2024, "period": "2024"}'

# Run a single pillar (e.g., just trade data)
temporal workflow start \
  --task-queue gii-pipeline \
  --type TradeDataWorkflow \
  --input '{"year": 2024, "period": "2024"}'

# List running workflows
temporal workflow list

# Get workflow status
temporal workflow show --workflow-id <workflow-id>

# Cancel a running workflow
temporal workflow cancel --workflow-id <workflow-id>
```

### Setting Up a Daily Schedule

To run the pipeline automatically on a recurring schedule:

```bash
# Create a schedule that runs daily at 02:00 UTC
temporal schedule create \
  --schedule-id gii-daily-refresh \
  --task-queue gii-pipeline \
  --workflow-type MainRefreshWorkflow \
  --input '{"year": 2025, "period": "2025"}' \
  --cron '0 2 * * *'

# List schedules
temporal schedule list

# Describe a schedule
temporal schedule describe --schedule-id gii-daily-refresh

# Trigger a scheduled workflow immediately (outside its cron)
temporal schedule trigger --schedule-id gii-daily-refresh

# Pause/unpause a schedule
temporal schedule toggle --schedule-id gii-daily-refresh --pause
temporal schedule toggle --schedule-id gii-daily-refresh --unpause

# Delete a schedule
temporal schedule delete --schedule-id gii-daily-refresh
```

### Monitoring Workflows

- **Temporal Web UI**: http://localhost:8080 — browse workflows, see activity history, inspect inputs/outputs, view errors
- **API status check**: `GET http://localhost:8000/api/pipelines/status` — confirms Temporal is reachable
- **Worker logs**: the worker process prints activity-level logs (`INFO` by default)

### Workflow Timeouts

| Activity | Timeout | Retries |
|----------|---------|---------|
| `fetch_and_store_trade` | 30 min | Heartbeat every 2 min |
| `fetch_and_store_flights` | 10 min | Default |
| `ingest_and_store_unwto` | 5 min | Default |
| `fetch_and_store_gdelt` | 15 min | Default |
| `compute_and_store_index` | 10 min | Default |
| `run_quality_check` | 5 min | Default |
| `generate_narratives` | 10 min | Default |

---

## Project Structure

```
src/gii/
  config.py            # Pydantic Settings (GII_ env prefix)
  models/              # Pydantic domain models
  data_sources/        # API clients (Comtrade, OpenFlights, UNWTO, GDELT)
  pipelines/           # Temporal workflows, activities, worker
  computation/         # Normalization + composite index math
  agents/              # LangChain quality + narrative agents (NVIDIA NIM or AWS Bedrock)
  api/                 # FastAPI routes
  dashboard/           # Jinja2 + HTMX templates
  storage/             # SQLAlchemy ORM + repository
```
