import json
import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

class AuditTools:
    """
    Collection of inspection tools for the Exception Auditor Agent.
    Operates over a thread-safe DuckDB cursor provided by Store.
    """
    def __init__(self, store):
        self.store = store
        try:
            self.conn = store.conn.cursor()
        except Exception:
            self.conn = store.conn

    def get_bank_transaction(self, txn_id: str) -> Dict[str, Any]:
        """
        Fetch details of a single bank transaction by txn_id.
        """
        try:
            df = self.conn.execute(
                "SELECT * FROM bank_txns WHERE txn_id = ?", [txn_id]
            ).df()
            if df.empty:
                return {"error": f"Transaction {txn_id} not found in bank_txns."}
            return json.loads(df.to_json(orient="records", date_format="iso"))[0]
        except Exception as e:
            logger.error(f"Error fetching bank transaction {txn_id}: {e}")
            return {"error": str(e)}

    def check_duplicate_bank_txns(
        self, txn_id: str, counterparty: Optional[str] = None, amount: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Check if there are other bank transactions with the same counterparty and amount,
        indicating a potential duplicate bank charge or statement import duplication.
        """
        try:
            if counterparty is None or amount is None:
                # If not provided, fetch from txn
                info = self.get_bank_transaction(txn_id)
                if "error" in info:
                    return []
                counterparty = info.get("counterparty", "")
                amount = float(info.get("amount", 0.0))

            query = """
                SELECT txn_id, date, amount, counterparty, description
                FROM bank_txns
                WHERE txn_id != ? AND ABS(amount - ?) <= 0.001
            """
            df = self.conn.execute(query, [txn_id, amount]).df()
            if df.empty:
                return []

            # Filter by counterparty similarity
            records = json.loads(df.to_json(orient="records", date_format="iso"))
            duplicates = []
            for rec in records:
                b_cp = str(rec.get("counterparty", ""))
                score = fuzz.ratio(str(counterparty).lower(), b_cp.lower())
                if score >= 75:
                    rec["counterparty_similarity"] = score
                    duplicates.append(rec)

            return duplicates
        except Exception as e:
            logger.error(f"Error checking duplicate bank transactions for {txn_id}: {e}")
            return []

    def search_gl_by_amount(
        self, amount: float, tolerance: float = 0.05, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search GL entries with amount within tolerance of the target amount.
        """
        try:
            query = """
                SELECT entry_id, date, amount, vendor_id, memo
                FROM gl_entries
                WHERE ABS(amount - ?) <= ?
                LIMIT ?
            """
            df = self.conn.execute(query, [amount, tolerance, limit]).df()
            if df.empty:
                return []
            return json.loads(df.to_json(orient="records", date_format="iso"))
        except Exception as e:
            logger.error(f"Error searching GL by amount {amount}: {e}")
            return []

    def search_gl_by_vendor(
        self, vendor_name: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search GL entries by vendor_id or memo text.
        """
        try:
            # Query candidate rows with non-null vendor_id or memo
            query = "SELECT entry_id, date, amount, vendor_id, memo FROM gl_entries"
            df = self.conn.execute(query).df()
            if df.empty:
                return []

            records = json.loads(df.to_json(orient="records", date_format="iso"))
            scored = []
            target = str(vendor_name).lower()

            for rec in records:
                v_id = str(rec.get("vendor_id", "")).lower()
                memo = str(rec.get("memo", "")).lower()
                s1 = fuzz.partial_ratio(target, v_id)
                s2 = fuzz.partial_ratio(target, memo)
                best_score = max(s1, s2)
                if best_score >= 60:
                    rec["match_score"] = best_score
                    scored.append(rec)

            scored.sort(key=lambda x: x["match_score"], reverse=True)
            return scored[:limit]
        except Exception as e:
            logger.error(f"Error searching GL by vendor {vendor_name}: {e}")
            return []

    def search_invoices(
        self, vendor_name: Optional[str] = None, amount: Optional[float] = None, tolerance: float = 0.05, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search invoices by vendor_id and/or amount within tolerance.
        """
        try:
            conditions = []
            params: List[Any] = []

            if amount is not None and amount > 0:
                conditions.append("ABS(amount - ?) <= ?")
                params.extend([amount, tolerance])

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM invoices {where_clause} LIMIT 50"
            df = self.conn.execute(query, params).df()
            if df.empty:
                return []

            records = json.loads(df.to_json(orient="records", date_format="iso"))
            if not vendor_name:
                return records[:limit]

            # Filter/score by vendor name
            target = str(vendor_name).lower()
            scored = []
            for rec in records:
                v_id = str(rec.get("vendor_id", "")).lower()
                score = fuzz.partial_ratio(target, v_id)
                if score >= 60:
                    rec["vendor_similarity"] = score
                    scored.append(rec)

            scored.sort(key=lambda x: x.get("vendor_similarity", 0), reverse=True)
            return scored[:limit] if scored else records[:limit]
        except Exception as e:
            logger.error(f"Error searching invoices: {e}")
            return []


# Tool declarations for OpenAI/Gemini tool calling schema
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_duplicate_bank_txns",
            "description": "Check if there are other identical bank transactions with the same counterparty and amount, indicating a duplicate charge or statement import.",
            "parameters": {
                "type": "object",
                "properties": {
                    "txn_id": {
                        "type": "string",
                        "description": "The current bank transaction ID being evaluated."
                    },
                    "counterparty": {
                        "type": "string",
                        "description": "The counterparty or merchant name."
                    },
                    "amount": {
                        "type": "number",
                        "description": "The exact bank transaction amount."
                    }
                },
                "required": ["txn_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_gl_by_amount",
            "description": "Search GL ledger entries that have an amount equal to or very close to the specified amount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The transaction amount to find in the General Ledger."
                    },
                    "tolerance": {
                        "type": "number",
                        "description": "Acceptable amount discrepancy tolerance (default 0.05)."
                    }
                },
                "required": ["amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_gl_by_vendor",
            "description": "Search GL ledger entries for a specific vendor name or keyword in the memo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor_name": {
                        "type": "string",
                        "description": "The vendor or counterparty name to match against GL entries."
                    }
                },
                "required": ["vendor_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_invoices",
            "description": "Search supplier/vendor invoices by vendor name and/or invoice amount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor_name": {
                        "type": "string",
                        "description": "The vendor name to search in invoices."
                    },
                    "amount": {
                        "type": "number",
                        "description": "The invoice amount to match."
                    },
                    "tolerance": {
                        "type": "number",
                        "description": "Amount tolerance (default 0.05)."
                    }
                }
            }
        }
    }
]
