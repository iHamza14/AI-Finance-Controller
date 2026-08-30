# AI Finance Controller

An intelligent, full-stack multi-source financial reconciliation engine. This tool ingests financial data (Bank Statements, GL Ledgers, and Invoices), automatically matches records using an ML classifier (XGBoost), and routes unresolved exceptions to an LLM-powered tool-calling agent for human-readable triage.

## 🚀 Tech Stack

- **Frontend:** Next.js, React, Tailwind CSS, Framer Motion, Lucide React
- **Backend:** Django REST Framework, Celery
- **Data & ML Core:** Pandas, Scikit-Learn, XGBoost, DuckDB
- **AI Agent:** LangGraph, Langchain (Groq/OpenAI)
- **Infrastructure:** Docker, PostgreSQL, Redis, `uv` (Dependency Management)

## 📁 Project Structure

```text
ai-finance-controller/
├── frontend/             # Next.js React Dashboard (Sleek UI)
├── backend/              # Django REST API & Celery Tasks
│   └── api/              # API endpoints, models, serializers, and tasks
├── core/                 # The ML & AI Agent Engine (Independent of web framework)
│   ├── agent/            # LangGraph exception triage agent
│   ├── features.py       # Vectorized feature engineering
│   └── ml_pipeline.py    # Pairwise matching pipeline
├── data/                 # Ephemeral storage for file uploads
├── docker-compose.yml    # Full stack orchestration
├── pyproject.toml        # `uv` Python dependencies
└── README.md
```

## 🛠 Getting Started (Docker - Recommended)

The easiest way to run the entire stack (Postgres, Redis, Celery, Django API, and Next.js Frontend) is via Docker Compose.

1. Ensure Docker Desktop is running.
2. Run the following command from the root directory:
   ```bash
   docker compose up --build
   ```
3. Access the Frontend Dashboard at [http://localhost:3000](http://localhost:3000).
4. *(The Backend API runs on `http://localhost:8000`)*.

## 💻 Getting Started (Local Native Dev)

If you prefer to run the services natively for development without Docker:

**1. Install Python Dependencies (Using `uv`)**
```bash
uv sync
```

**2. Start Redis**
Ensure you have Redis running locally (e.g., `brew services start redis`).

**3. Start the Django API**
```bash
cd backend
uv run python manage.py migrate
uv run python manage.py runserver
```

**4. Start the Celery Worker (In a new terminal)**
```bash
cd backend
uv run celery -A finance_backend worker -l info
```

**5. Start the Frontend (In a new terminal)**
```bash
cd frontend
npm install
npm run dev
```

## 🧠 How It Works
1. **Upload:** User drops 3 CSVs (Bank, GL, Invoices) into the sleek frontend dashboard.
2. **Ingest:** Files are sent to the Django `/api/reconcile/start/` endpoint, returning a Job UUID.
3. **Machine Learning:** Celery spins up a background worker, loading the data into pandas and evaluating candidate matches using the pre-trained XGBoost model.
4. **Agent Triage:** Transactions scoring below the confidence threshold fall through to the LangGraph AI agent, which queries the DuckDB ledger to write an investigation report.
5. **Report:** The frontend polls the Django API, fetching the completed `ReconciliationReport` JSON from Postgres, displaying match rates and the exception list beautifully.
