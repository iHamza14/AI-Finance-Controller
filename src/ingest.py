import os
import pandas as pd

def ingest_data(data_dir="data"):
    """
    Load raw CSV data into pandas DataFrames.
    Includes basic schema validation/type casting.
    """
    bank_path = os.path.join(data_dir, "bank_statements.csv")
    gl_path = os.path.join(data_dir, "gl_ledger.csv")
    invoice_path = os.path.join(data_dir, "invoices.csv")
    
    if not all(os.path.exists(p) for p in [bank_path, gl_path, invoice_path]):
        raise FileNotFoundError("Missing one or more data files. Run generate_dataset.py first.")
        
    bank_df = pd.read_csv(bank_path, parse_dates=["date"])
    gl_df = pd.read_csv(gl_path, parse_dates=["date"])
    invoice_df = pd.read_csv(invoice_path, parse_dates=["date"])
    
    return bank_df, gl_df, invoice_df
