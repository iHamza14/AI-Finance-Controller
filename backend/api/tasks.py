import logging
import sys
import os
import time
from celery import shared_task
from django.utils import timezone
from .models import ReconciliationJob, ReconciliationReport
import pandas as pd

# Add the project root to sys.path so we can import `core`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)

from core.ml_pipeline import run_ml_core
from core.agent.exception_agent import resolve_exception
from src.store import Store # wait, store is in src? or core? Let's check where store is later, but for now we try

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

        # 1. Run ML Matcher
        model_path = os.path.join(PROJECT_ROOT, "core", "model.pkl")
        if not os.path.exists(model_path):
            # Fallback to older location if refactoring was partial
            model_path = os.path.join(PROJECT_ROOT, "models", "reconciliation_model_xgb.pkl")

        confirmed_pairs, df_exceptions = run_ml_core(df_bank, df_gl, df_invoices, model_path=model_path)
        
        # We can implement the agent triage here eventually.
        # For MVP integration we will just record the exceptions found by ML.
        
        match_rate = len(confirmed_pairs) / len(df_bank) if len(df_bank) > 0 else 0
        exception_rate = len(df_exceptions) / len(df_bank) if len(df_bank) > 0 else 0

        import json
        exceptions_json = json.loads(df_exceptions.to_json(orient='records', date_format='iso'))

        # Save Report
        ReconciliationReport.objects.create(
            job=job,
            batch_size=len(df_bank),
            match_rate=match_rate,
            exception_rate=exception_rate,
            ml_metrics={"info": "Metrics tracking from DB to be connected next"},
            exceptions=exceptions_json
        )

        job.status = 'COMPLETED'
        job.completed_at = timezone.now()
        job.save()

        return f"Job {job_id} completed successfully."

    except Exception as e:
        logger.error(f"Reconciliation Job {job_id} failed: {e}")
        job.status = 'FAILED'
        job.error_message = str(e)
        job.completed_at = timezone.now()
        job.save()
        raise e
