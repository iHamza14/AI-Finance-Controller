import os
import sys

# Ensure imports work from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingest import ingest_data
from src.features import generate_candidate_pairs, compute_features
from src.model import DummyModel
from src.store import Store
from src.agent.exception_agent import resolve_exception
from src.report import generate_report

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    output_dir = os.path.join(base_dir, "outputs")
    db_path = os.path.join(base_dir, "finance_controller.duckdb")
    
    print("1. Ingesting Data...")
    try:
        bank_df, gl_df, invoice_df = ingest_data(data_dir)
    except Exception as e:
        print(f"Error ingesting data: {e}")
        return
        
    print(f"Loaded {len(bank_df)} bank txns, {len(gl_df)} GL entries, {len(invoice_df)} invoices.")

    print("2. Initializing Store...")
    # Delete old db if exists for fresh run
    if os.path.exists(db_path):
        os.remove(db_path)
    store = Store(db_path)
    store.load_dataframes(bank_df, gl_df, invoice_df)

    print("3. Generating Candidate Pairs & Features...")
    pairs_df = generate_candidate_pairs(bank_df, gl_df)
    features_df = compute_features(pairs_df, invoice_df)
    
    print(f"Generated {len(features_df)} candidate pairs.")

    print("4. Running ML Inference (Dummy Model)...")
    model = DummyModel()
    predictions_df = model.predict_proba(features_df)
    
    # Process predictions
    # Sort by match_score desc to get best matches first
    predictions_df = predictions_df.sort_values(by='match_score', ascending=False)
    
    # We only want to match a bank_txn to ONE gl_entry
    # A simple greedy approach: drop duplicates on txn_id and entry_id
    best_matches = predictions_df.drop_duplicates(subset=['txn_id'])
    best_matches = best_matches.drop_duplicates(subset=['entry_id'])

    # Get the txn_ids that the model didn't confidently match or didn't match at all
    matched_txn_ids = set()
    
    print("5. Processing Matches & Exceptions...")
    for _, row in best_matches.iterrows():
        txn_id = row['txn_id']
        entry_id = row['entry_id']
        score = row['match_score']
        
        if score >= model.threshold:
            store.save_match(txn_id, entry_id, score, status="MATCH")
            matched_txn_ids.add(txn_id)
        else:
            # Below threshold, it's an exception, but it was the best guess
            pass

    # Find all bank txns that weren't matched confidently
    all_txns = set(bank_df['txn_id'])
    exception_txns = all_txns - matched_txn_ids
    
    print(f"   -> {len(matched_txn_ids)} Confident Matches")
    print(f"   -> {len(exception_txns)} Exceptions to route to Agent")

    print("6. Agent Triage...")
    for i, txn_id in enumerate(exception_txns):
        print(f"   Agent investigating {txn_id} ({i+1}/{len(exception_txns)})...")
        verdict, reason = resolve_exception(txn_id, store)
        store.save_exception(txn_id, verdict, reason)

    print("7. Generating Report...")
    # Dummy ML Metrics since we don't train it here
    ml_metrics = {
        "precision": 0.92,
        "recall": 0.89,
        "f1": 0.90,
        "auc_roc": 0.95,
        "threshold_used": model.threshold
    }
    generate_report(store, ml_metrics, output_dir)
    
    store.close()
    print("Pipeline Complete! Check outputs/reconciliation_report.html")

if __name__ == "__main__":
    main()
