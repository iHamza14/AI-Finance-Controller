import pandas as pd
from core.ml_pipeline import run_ml_core

def run_quick_test():
    print("1. Loading sample data (first 100 bank txns)...")
    # Load a small batch of bank txns to test speed, but load the full GL/Invoices to ensure matches exist
    df_bank = pd.read_csv("data/bank_statements.csv").head(100)
    df_gl = pd.read_csv("data/gl_ledger.csv")
    df_invoices = pd.read_csv("data/invoices.csv")
    
    print("2. Running Vectorized ML Pipeline...")
    # This will trigger build_features, load_model, and predict_and_route
    confirmed_pairs, df_exceptions = run_ml_core(
        df_bank, 
        df_gl, 
        df_invoices, 
        model_path="core/model.pkl"
    )
    
    print("\n=== PIPELINE RESULTS ===")
    print(f"Total Bank Txns Processed : {len(df_bank)}")
    print(f"Auto-Matched (Confirmed)  : {len(confirmed_pairs)}")
    print(f"Exceptions (For Agent)    : {len(df_exceptions)}")
    
    # Verify the structure matches the new backend expectations
    if confirmed_pairs:
        print("\n=== SAMPLE OUTPUT STRUCTURE ===")
        print("Confirmed Pair (Ready for DB Insert):")
        print(confirmed_pairs[0]) 
        # Expected format: {'txn_id': 'TXN_001', 'entry_id': 'GL_005'}
        
    if not df_exceptions.empty:
        print("\nException DataFrame (Ready for LangGraph Queue):")
        print(df_exceptions[['txn_id', 'amount', 'counterparty']].head(2))

if __name__ == "__main__":
    run_quick_test()