import pandas as pd
import unittest
from src.store import Store
from core.agent.tools import AuditTools
from core.agent.exception_agent import ExceptionAuditorAgent, resolve_exception, resolve_exceptions_batch

class TestExceptionAgent(unittest.TestCase):
    def setUp(self):
        # Create an in-memory Store with mock tables
        self.store = Store(db_path=":memory:")
        
        # 1. Mock Bank Transactions
        # TXN_001: Duplicate payment
        # TXN_002: Real payment of TXN_001
        # TXN_003: Unmatched exception that actually matches GL_003 (vendor mismatch/slight spelling)
        # TXN_004: True anomaly / missing GL
        self.df_bank = pd.DataFrame([
            {
                "txn_id": "TXN_001",
                "date": "2026-03-01",
                "amount": 150.00,
                "counterparty": "Amazon Web Services",
                "description": "AWS Cloud Services March"
            },
            {
                "txn_id": "TXN_002",
                "date": "2026-03-01",
                "amount": 150.00,
                "counterparty": "Amazon Web Services",
                "description": "AWS Cloud Services March (Duplicate)"
            },
            {
                "txn_id": "TXN_003",
                "date": "2026-03-02",
                "amount": 420.50,
                "counterparty": "Salesforce.com",
                "description": "CRM Subscription"
            },
            {
                "txn_id": "TXN_004",
                "date": "2026-03-05",
                "amount": 9999.00,
                "counterparty": "Unknown Vendor X",
                "description": "Wire transfer out"
            }
        ])

        # 2. Mock GL Entries
        self.df_gl = pd.DataFrame([
            {
                "entry_id": "GL_001",
                "date": "2026-03-01",
                "amount": 150.00,
                "vendor_id": "Amazon Web Services",
                "memo": "AWS Hosting"
            },
            {
                "entry_id": "GL_003",
                "date": "2026-03-02",
                "amount": 420.50,
                "vendor_id": "Salesforce Inc",
                "memo": "CRM Monthly License"
            }
        ])

        # 3. Mock Invoices
        self.df_invoices = pd.DataFrame([
            {
                "invoice_id": "INV_101",
                "vendor_id": "Amazon Web Services",
                "amount": 150.00,
                "date": "2026-03-01"
            },
            {
                "invoice_id": "INV_102",
                "vendor_id": "Salesforce Inc",
                "amount": 420.50,
                "date": "2026-03-02"
            }
        ])

        self.store.load_dataframes(self.df_bank, self.df_gl, self.df_invoices)
        self.tools = AuditTools(self.store)

    def tearDown(self):
        self.store.close()

    def test_tool_duplicate_detection(self):
        dups = self.tools.check_duplicate_bank_txns("TXN_001", "Amazon Web Services", 150.00)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["txn_id"], "TXN_002")

    def test_tool_search_gl_by_amount(self):
        matches = self.tools.search_gl_by_amount(420.50, tolerance=0.01)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["entry_id"], "GL_003")

    def test_tool_search_gl_by_vendor(self):
        matches = self.tools.search_gl_by_vendor("Salesforce.com")
        self.assertTrue(len(matches) > 0)
        self.assertEqual(matches[0]["entry_id"], "GL_003")

    def test_audit_duplicate_bank_txn(self):
        # TXN_002 is duplicate of TXN_001
        res = resolve_exception("TXN_002", self.store)
        verdict, reason = res
        self.assertEqual(verdict, "DUPLICATE_FLAG")
        self.assertIn("TXN_001", reason)
        self.assertIsNone(res.matched_entry_id)

    def test_audit_resolved_with_confidence(self):
        # TXN_003 matches GL_003
        res = resolve_exception("TXN_003", self.store)
        verdict, reason = res
        self.assertEqual(verdict, "RESOLVED_WITH_CONFIDENCE")
        self.assertEqual(res.matched_entry_id, "GL_003")

    def test_audit_needs_human(self):
        # TXN_004 has no GL entry
        res = resolve_exception("TXN_004", self.store)
        verdict, reason = res
        self.assertEqual(verdict, "NEEDS_HUMAN")
        self.assertIsNone(res.matched_entry_id)

    def test_resolve_exceptions_batch(self):
        exceptions = [
            {"txn_id": "TXN_002", "amount": 150.00, "counterparty": "Amazon Web Services"},
            {"txn_id": "TXN_003", "amount": 420.50, "counterparty": "Salesforce.com"},
            {"txn_id": "TXN_004", "amount": 9999.00, "counterparty": "Unknown Vendor X"}
        ]
        results = resolve_exceptions_batch(exceptions, self.store, max_workers=2)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["agent_verdict"], "DUPLICATE_FLAG")
        self.assertEqual(results[1]["agent_verdict"], "RESOLVED_WITH_CONFIDENCE")
        self.assertEqual(results[1]["matched_entry_id"], "GL_003")
        self.assertEqual(results[2]["agent_verdict"], "NEEDS_HUMAN")

if __name__ == "__main__":
    unittest.main()
