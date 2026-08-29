import duckdb
import os
import pandas as pd
from datetime import datetime

class Store:
    def __init__(self, db_path="finance_controller.duckdb"):
        self.conn = duckdb.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        # We can create tables directly from pandas DataFrames later,
        # but for match results and exceptions, we should define schemas.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS match_results (
                txn_id VARCHAR,
                entry_id VARCHAR,
                score DOUBLE,
                status VARCHAR,
                resolved_by VARCHAR,
                timestamp TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exceptions (
                txn_id VARCHAR,
                agent_verdict VARCHAR,
                reason TEXT,
                timestamp TIMESTAMP
            )
        """)

    def load_dataframes(self, bank_df, gl_df, invoice_df):
        """Load raw CSV data into DuckDB tables."""
        # DuckDB can register pandas DataFrames as virtual tables
        self.conn.register("bank_df_view", bank_df)
        self.conn.register("gl_df_view", gl_df)
        self.conn.register("invoice_df_view", invoice_df)
        
        self.conn.execute("CREATE OR REPLACE TABLE bank_txns AS SELECT * FROM bank_df_view")
        self.conn.execute("CREATE OR REPLACE TABLE gl_entries AS SELECT * FROM gl_df_view")
        self.conn.execute("CREATE OR REPLACE TABLE invoices AS SELECT * FROM invoice_df_view")
        
    def save_match(self, txn_id, entry_id, score, status, resolved_by="model"):
        """Save a confirmed match."""
        timestamp = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO match_results VALUES (?, ?, ?, ?, ?, ?)",
            [txn_id, entry_id, score, status, resolved_by, timestamp]
        )

    def save_exception(self, txn_id, agent_verdict, reason):
        """Save an exception resolved by the agent."""
        timestamp = datetime.now().isoformat()
        self.conn.execute(
            "INSERT INTO exceptions VALUES (?, ?, ?, ?)",
            [txn_id, agent_verdict, reason, timestamp]
        )

    def get_exception_summary(self):
        """Return exceptions as a list of dicts for reporting."""
        return self.conn.execute("""
            SELECT e.txn_id, b.amount, b.counterparty, e.agent_verdict, e.reason
            FROM exceptions e
            JOIN bank_txns b ON e.txn_id = b.txn_id
        """).df().to_dict('records')

    def close(self):
        self.conn.close()

# For easy import of a singleton instance if needed
# db = Store()
