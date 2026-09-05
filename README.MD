# AI Finance Controller — Autonomous Financial Reconciliation System

**Version Architecture**

AI Finance Controller is a full-stack, multi-source financial reconciliation platform built on a Django REST architecture, backed by Celery asynchronous workers, and driven by a hybrid Machine Learning & LLM Agent engine.

The system autonomously ingests fragmented financial data (Bank Statements, General Ledgers, and Invoices), executes deterministic pairs matching using a Gradient Boosting/XGBoost classifier, and routes unresolved anomalies (exceptions) to an LLM-powered batch triage agent. The agent dynamically cross-references missing data via DuckDB, assigns strict resolution statuses, and generates actionable, human-readable audit trails.

---

## 🌟 Key Features

*   **🛡️ Deterministic ML Core:** The bulk of clear-cut reconciliations are handled instantly by an offline Scikit-Learn/XGBoost pipeline, bypassing expensive LLM calls for standard matches to guarantee high-throughput processing.
*   **🧠 Hybrid AI Exception Triage:** Unmatched anomalies are batched and routed to an LLM agent (Gemini 3.6 Flash) that acts as an AI Accountant. It uses pre-fetched contextual data from an in-memory DuckDB to diagnose root causes (e.g., missing GL entries, exact amount mismatches).
*   **⚡ Bounded Action Space:** The AI agent operates strictly within an enumerable status catalog (`MATCHED`, `RESOLVED_WITH_CONFIDENCE`, `DUPLICATE_FLAG`, `NEEDS_HUMAN`), ensuring zero out-of-policy hallucinated states.
*   **🔀 Asynchronous Event Driven Pipeline:** A robust Celery + Redis message broker architecture ensures that heavy ML and LLM workloads execute reliably in the background without blocking the UI, complete with Postgres-backed job tracking.
*   **📊 Real-Time Glassmorphic Dashboard:** Interactive Django templates driven by Vanilla JS and Tailwind CSS, featuring live job status polling, interactive KPI cards (Match Rates, Exception Rates), and a clean drag-and-drop file upload interface.

---

## 📁 Directory Structure

```text
ai-finance-controller/
├── backend/
│   ├── finance_backend/          # Django core settings & ASGI/WSGI
│   ├── api/                      # Django App (Routes, Models, Tasks)
│   │   ├── models.py             # Persistent schemas (ReconciliationJob, Report)
│   │   ├── views.py              # REST API endpoints
│   │   ├── tasks.py              # Celery worker definitions & LLM Triage logic
│   │   └── templates/
│   │       └── api/dashboard.html # Primary glassmorphic dashboard view
│   └── manage.py
├── core/
│   ├── features.py               # Vectorized feature engineering for ML
│   └── ml_pipeline.py            # Pairwise matching pipeline & XGBoost execution
├── src/
│   └── store.py                  # DuckDB in-memory analytical engine for LLM context
├── data/
│   ├── ground_truth.csv          # Evaluation and synthetic testing data
│   └── <job-id>/                 # Ephemeral storage for active reconciliation jobs
├── models/
│   └── reconciliation_model_xgb.pkl # Pre-trained ML classifier weights
├── pyproject.toml                # `uv` Python dependency configuration
├── docker-compose.yml            # Full stack orchestration (Postgres, Redis, Web, Celery)
└── README.md
```

---

## 🚀 Quickstart & Running Locally

### Option 1: Using Docker Compose (Recommended)

1. **Configure Environment:** Ensure you have a `.env` file in the root directory (copy from `.env.example`).
   ```bash
   export GEMINI_API_KEY="your_gemini_api_key_here"
   ```

2. **Start the Stack:** Spin up PostgreSQL, Redis, the FastAPI/Django backend, and Celery workers in one command.
   ```bash
   docker-compose up --build
   ```

3. **Access the Dashboard:** Open your browser and navigate to [http://localhost:8000](http://localhost:8000).

### Option 2: Running Natively for Development

If you prefer to run services natively on your host machine:

1. **Install Dependencies:**
   ```bash
   uv sync
   ```

2. **Start Infrastructure:** Ensure Redis and PostgreSQL are running locally on their default ports.

3. **Start the Backend Server:**
   ```bash
   cd backend
   uv run python manage.py runserver
   ```

4. **Start the Celery Worker (New Terminal):**
   ```bash
   cd backend
   uv run celery -A finance_backend worker -l info
   ```

---

## 📋 Demo Script & Judging Checklist

*   **Journey 1 — Clean Autonomous ML Match:** Upload standard CSVs. The ML GradientBoosting model instantly matches TXN_001 (Bank) with GL_001 with 99% accuracy. Labeled as `MATCHED` with reason "ML Auto-Matched". No LLM tokens consumed.
*   **Journey 2 — LLM Diagnostic Triage:** TXN_011 is rejected by the ML model due to a missing GL ledger entry. The Celery worker routes it to Gemini 3.6 Flash. The agent cross-references the `invoices.csv` context via DuckDB, detects the matching invoice, and flags it as `RESOLVED_WITH_CONFIDENCE` with an exact audit trail explanation.
*   **Journey 3 — Escalation & Stopping Rules:** TXN_002 has no matching amount in either the GL or Invoices. The AI agent strictly adheres to its bounded action space, stopping its search and safely escalating the transaction as `NEEDS_HUMAN` to prevent hallucinated matches.
