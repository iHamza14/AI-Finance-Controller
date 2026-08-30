# AI Finance Controller

An intelligent, full-stack multi-source financial reconciliation engine. This tool ingests financial data (Bank Statements, GL Ledgers, and Invoices), automatically matches records using an ML classifier (XGBoost), and routes unresolved exceptions to an LLM-powered tool-calling agent for human-readable triage.

## 🚀 Tech Stack

- **Frontend:** Django Templates, Vanilla JS, Tailwind CSS (via CDN)
- **Backend:** Django REST Framework, Celery
- **Data & ML Core:** Pandas, Scikit-Learn, XGBoost, DuckDB
- **AI Agent:** Batch Processing with Gemini (gemini-3.6-flash)
- **Infrastructure:** Docker, PostgreSQL, Redis, `uv` (Dependency Management)

## 📁 Project Structure

```text
ai-finance-controller/
├── backend/              # Django Web Server (API, Templates, Celery Tasks)
│   ├── api/              
│   │   ├── templates/api/dashboard.html  # Frontend UI
│   │   └── tasks.py                      # Celery workers
├── core/                 # The ML Engine
│   ├── features.py       # Vectorized feature engineering
│   └── ml_pipeline.py    # Pairwise matching pipeline
├── data/                 # Ephemeral storage for file uploads
├── docker-compose.yml    # Full stack orchestration
├── pyproject.toml        # `uv` Python dependencies
└── README.md
```

## 🛠 Getting Started (Docker - Recommended)

The easiest way to run the entire stack (Postgres, Redis, Celery, and Django) is via Docker Compose.

1. Ensure Docker Desktop is running.
2. Run the following command from the root directory:
   ```bash
   docker compose up --build
   ```
3. Access the Dashboard at [http://localhost:8000](http://localhost:8000).

## 💻 Getting Started (Local Native Dev)

If you prefer to run the services natively for development without Docker:

**1. Install Python Dependencies (Using `uv`)**
```bash
uv sync
```

**2. Start Redis**
Ensure you have Redis running locally.

**3. Start the Django Server**
```bash
cd backend
uv run python manage.py runserver
```

**4. Start the Celery Worker (In a new terminal)**
```bash
cd backend
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run celery -A finance_backend worker -l info
```

## 🧠 How It Works
1. **Upload:** User drops 3 CSVs (Bank, GL, Invoices) into the Django HTML dashboard at `localhost:8000`.
2. **Ingest:** Files are sent to the Django `/api/reconcile/start/` REST endpoint.
3. **Machine Learning:** Celery spins up a background worker, evaluates candidate matches using the pre-trained XGBoost model.
4. **Agent Triage (Batch Mode):** Anomalies fall through to a batch processor, which pre-fetches ledger context via DuckDB and sends a single, lightning-fast API request to Gemini 3.6 to generate triage verdicts.
5. **Report:** The Vanilla JS frontend polls the Django API, fetching the `ReconciliationReport` JSON from Postgres, displaying it beautifully.
