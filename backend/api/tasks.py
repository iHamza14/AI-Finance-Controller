import logging
import sys
import os
import time
import json
import pandas as pd
from celery import shared_task
from django.utils import timezone
from .models import ReconciliationJob, ReconciliationReport
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from django.utils import timezone
from .models import ReconciliationJob, ReconciliationReport
from dotenv import load_dotenv

# Add the project root to sys.path so we can import `core`
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)

# Ensure environment variables (like GROQ_API_KEY) are loaded
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from core.ml_pipeline import run_ml_core
from src.store import Store 

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
            model_path = os.path.join(PROJECT_ROOT, "models", "reconciliation_model_xgb.pkl")

        confirmed_pairs, df_exceptions = run_ml_core(df_bank, df_gl, df_invoices, model_path=model_path)
        
        # 2. Agent Triage (BATCH MODE)
        store = Store(db_path=":memory:")
        store.load_dataframes(df_bank, df_gl, df_invoices)
        exception_records = json.loads(df_exceptions.to_json(orient='records', date_format='iso'))
        
        exceptions_list = []
        
        if len(exception_records) > 0:
            batch_payload = []
            for ex in exception_records:
                amt = ex["amount"]
                gl_matches = store.conn.execute(f"SELECT * FROM gl_entries WHERE amount = {amt} LIMIT 3").df()
                inv_matches = store.conn.execute(f"SELECT * FROM invoices WHERE amount = {amt} LIMIT 3").df()
                
                context_item = {
                    "txn_id": ex["txn_id"],
                    "date": ex.get("date"),
                    "counterparty": ex.get("counterparty"),
                    "amount": ex["amount"],
                    "potential_gl_matches": json.loads(gl_matches.to_json(orient="records")) if not gl_matches.empty else [],
                    "potential_invoice_matches": json.loads(inv_matches.to_json(orient="records")) if not inv_matches.empty else []
                }
                batch_payload.append(context_item)

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set in your .env file!")
                
            llm = ChatOpenAI(
                model="gemini-3.6-flash",
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                temperature=0
            )
            
            prompt = f'''You are an expert AI Finance Controller. 
Review this batch of unmatched bank transactions. We have pre-fetched potential matches from the GL and Invoices based on the exact amount.
Decide a status for each transaction:
1. RESOLVED_WITH_CONFIDENCE: If a potential match clearly matches the counterparty or date.
2. DUPLICATE_FLAG: If it looks like a duplicate.
3. NEEDS_HUMAN: If no match makes sense.

Return ONLY a JSON array of objects, with NO markdown formatting, like this:
[
  {{"txn_id": "TXN_001", "status": "NEEDS_HUMAN", "reason": "No matching GL found"}},
  ...
]

Transactions to triage:
{json.dumps(batch_payload, indent=2, default=str)}
'''
            
            import logging
            logging.info(f"Sending batch of {len(exception_records)} exceptions to Gemini...")
            
            try:
                response = llm.invoke(prompt)
                content_resp = response.content
                import re
                match = re.search(r'\[.*\]', content_resp, re.DOTALL)
                if match:
                    results = json.loads(match.group(0))
                else:
                    results = json.loads(content_resp)
                    
                result_map = {r.get("txn_id"): r for r in results if isinstance(r, dict)}
                for ex in exception_records:
                    res = result_map.get(ex["txn_id"], {})
                    ex["agent_verdict"] = res.get("status", "NEEDS_HUMAN")
                    ex["reason"] = res.get("reason", "No reasoning provided.")
                    exceptions_list.append(ex)
                    
            except Exception as e:
                logging.error(f"Batch LLM failed: {str(e)}")
                for ex in exception_records:
                    ex["agent_verdict"] = "ERROR"
                    ex["reason"] = f"Batch API failed: {str(e)}"
                    exceptions_list.append(ex)
        
        # Generate final_results.csv
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
                df_ex['entry_id'] = ''
                if 'reason' not in df_ex.columns:
                    df_ex['reason'] = ''
                frames.append(df_ex[['txn_id', 'entry_id', 'status', 'reason']])
            if frames:
                pd.concat(frames, ignore_index=True).to_csv(os.path.join(data_dir, 'final_results.csv'), index=False)
        except Exception as e:
            import logging
            logging.error(f"Failed to save CSV: {e}")

        match_rate = len(confirmed_pairs) / len(df_bank) if len(df_bank) > 0 else 0
        exception_rate = len(df_exceptions) / len(df_bank) if len(df_bank) > 0 else 0

        # Save Report
        ReconciliationReport.objects.create(
            job=job,
            batch_size=len(df_bank),
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
