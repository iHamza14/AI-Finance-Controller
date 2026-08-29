from langchain_core.tools import tool
from rapidfuzz import fuzz
import json

def get_agent_tools(store):
    """
    Returns a list of tools bound to the current DuckDB store instance.
    """

    @tool
    def lookup_invoice(vendor_id: str, min_amount: float, max_amount: float) -> str:
        """Looks up invoices for a specific vendor within an amount range."""
        try:
            df = store.conn.execute(
                f"""
                SELECT * FROM invoices 
                WHERE vendor_id = '{vendor_id}' 
                AND amount >= {min_amount} 
                AND amount <= {max_amount}
                """
            ).df()
            if df.empty:
                return "No matching invoices found."
            return df.to_json(orient="records")
        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def check_duplicate(txn_id: str) -> str:
        """Checks if a bank transaction might be a duplicate of another recent transaction (same amount and counterparty)."""
        try:
            # First get the details of the txn_id
            target_df = store.conn.execute(f"SELECT * FROM bank_txns WHERE txn_id = '{txn_id}'").df()
            if target_df.empty:
                return "Transaction not found."
            
            amt = target_df.iloc[0]['amount']
            cp = target_df.iloc[0]['counterparty']
            date = target_df.iloc[0]['date']
            
            # Now find others
            dups = store.conn.execute(
                f"""
                SELECT * FROM bank_txns 
                WHERE counterparty = '{cp}' 
                AND amount = {amt}
                AND txn_id != '{txn_id}'
                """
            ).df()
            
            # Check date within 3 days
            if not dups.empty:
                dups['date'] = pd.to_datetime(dups['date'])
                target_date = pd.to_datetime(date)
                dups = dups[(dups['date'] - target_date).dt.days.abs() <= 3]
                
            if dups.empty:
                return "No duplicates found."
            return f"Potential duplicates found: {dups['txn_id'].tolist()}"
        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def query_ledger(account_code: str = None, min_amount: float = None, max_amount: float = None) -> str:
        """Queries the GL ledger based on filters to find missing bookings."""
        query = "SELECT * FROM gl_entries WHERE 1=1"
        if account_code:
            query += f" AND account_code = '{account_code}'"
        if min_amount is not None:
            query += f" AND amount >= {min_amount}"
        if max_amount is not None:
            query += f" AND amount <= {max_amount}"
            
        try:
            df = store.conn.execute(query).df()
            if df.empty:
                return "No matching GL entries found."
            # Return top 5 to avoid context overflow
            return df.head(5).to_json(orient="records")
        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def fuzzy_vendor_search(name: str) -> str:
        """Searches for a vendor name in the GL using fuzzy string matching."""
        try:
            vendors = store.conn.execute("SELECT DISTINCT vendor_id, memo FROM gl_entries").df()
            if vendors.empty:
                return "No vendors found in GL."
                
            matches = []
            for _, row in vendors.iterrows():
                score = fuzz.ratio(name.lower(), str(row['memo']).lower())
                if score >= 60:  # threshold
                    matches.append({"vendor_id": row['vendor_id'], "memo": row['memo'], "score": score})
            
            if not matches:
                return "No fuzzy matches found."
                
            matches = sorted(matches, key=lambda x: x['score'], reverse=True)
            return json.dumps(matches[:3])
        except Exception as e:
            return f"Error: {str(e)}"

    return [lookup_invoice, check_duplicate, query_ledger, fuzzy_vendor_search]

import pandas as pd
