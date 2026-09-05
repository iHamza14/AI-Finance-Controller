import logging
import sys
import os
import json
import pandas as pd
from celery import shared_task
from django.utils import timezone
from .models import ReconciliationJob, ReconciliationReport
from dotenv import load_dotenv

# Add the project root to sys.path so we can import `core`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from core.ml_pipeline import run_ml_core
from src.store import Store 
from core.agent.exception_agent import resolve_exceptions_batch

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def run_reconciliation_pipeline(self, job_id, data_dir):
    """
    Celery task to run the AI Finance Controller core ML/Agent pipeline.
    """
    job = ReconciliationJob.objects.get(id=job_id)
    job.status = 'RUNNING'
    job.save()

    try:
        bank_path = os.path.join(data_dir, 'bank_statements.csv')
        gl_path = os.path.join(data_dir, 'gl_ledger.csv')
        invoices_path = os.path.join(data_dir, 'invoices.csv')

        df_bank = pd.read_csv(bank_path)
        df_gl = pd.read_csv(gl_path)
        df_invoices = pd.read_csv(invoices_path)

        total_bank_rows = len(df_bank)

        # 0. Intercept Duplicates Deterministically
        dup_mask = df_bank.duplicated(subset=['amount', 'counterparty', 'date'], keep='first')
        df_duplicates = df_bank[dup_mask].copy()
        
        # Remove duplicates from the bank statement so the ML model doesn't see them
        df_bank = df_bank[~dup_mask].copy()

        # 1. Run ML Matcher
        model_path = os.path.join(PROJECT_ROOT, "core", "model.pkl")
        if not os.path.exists(model_path):
            model_path = os.path.join(PROJECT_ROOT, "models", "reconciliation_model_xgb.pkl")

        confirmed_pairs, df_exceptions = run_ml_core(df_bank, df_gl, df_invoices, model_path=model_path)
        
        # 2. Setup Database Context (DuckDB) for MCP Agent
        store = Store(db_path=":memory:")
        store.load_dataframes(df_bank, df_gl, df_invoices)
        exception_records = json.loads(df_exceptions.to_json(orient='records', date_format='iso'))
        
        # 3. Agent Triage via MCP Architecture
        exceptions_list = []
        if len(exception_records) > 0:
            logger.info(f"Routing {len(exception_records)} exceptions to the MCP Autonomous Agent...")
            # We use max_workers=4 for concurrent LLM API calls via the agent
            exceptions_list = resolve_exceptions_batch(exception_records, store, max_workers=4)
            
        # Append the intercepted duplicates directly to the final agent list
        if not df_duplicates.empty:
            dup_records = json.loads(df_duplicates.to_json(orient='records', date_format='iso'))
            for rec in dup_records:
                rec["agent_verdict"] = "DUPLICATE_FLAG"
                rec["reason"] = "Deterministic duplicate caught: Exact match on amount, counterparty, and date."
                rec["matched_entry_id"] = None
                exceptions_list.append(rec)
        
        # 4. Generate final_results.csv
        try:
            frames = []
            if confirmed_pairs:
                df_conf = pd.DataFrame(confirmed_pairs)
                df_conf['status'] = 'MATCHED'
                df_conf['reason'] = 'ML Auto-Matched'
                frames.append(df_conf[['txn_id', 'entry_id', 'status', 'reason']])
            if exceptions_list:
                df_ex = pd.DataFrame(exceptions_list)
                if 'agent_verdict' in df_ex.columns:
                    df_ex['status'] = df_ex['agent_verdict']
                else:
                    df_ex['status'] = 'NEEDS_HUMAN'
                
                # Use matched_entry_id if the agent found it, otherwise blank
                if 'matched_entry_id' in df_ex.columns:
                    df_ex['entry_id'] = df_ex['matched_entry_id']
                else:
                    df_ex['entry_id'] = ''
                
                if 'reason' not in df_ex.columns:
                    df_ex['reason'] = ''
                frames.append(df_ex[['txn_id', 'entry_id', 'status', 'reason']])
            
            if frames:
                pd.concat(frames, ignore_index=True).to_csv(os.path.join(data_dir, 'final_results.csv'), index=False)
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")

        match_rate = len(confirmed_pairs) / total_bank_rows if total_bank_rows > 0 else 0
        exception_rate = len(df_exceptions) / total_bank_rows if total_bank_rows > 0 else 0

        # Save Report
        ReconciliationReport.objects.create(
            job=job,
            batch_size=total_bank_rows,
            match_rate=match_rate,
            exception_rate=exception_rate,
            ml_metrics={"info": "Metrics tracking from DB to be connected next"},
            exceptions=exceptions_list
        )

        job.status = 'COMPLETED'
        job.completed_at = timezone.now()
        job.save()
        
        # Close DuckDB connection
        store.close()

        return f"Job {job_id} completed successfully."

    except Exception as e:
        logger.error(f"Reconciliation Job {job_id} failed: {e}")
        job.status = 'FAILED'
        job.error_message = str(e)
        job.completed_at = timezone.now()
        job.save()
        raise e
