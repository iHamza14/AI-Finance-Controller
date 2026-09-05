import json
import unittest
import pandas as pd
from src.store import Store
from core.agent.mcp_server import FinanceMCPServer

class TestFinanceMCPServer(unittest.TestCase):
    def setUp(self):
        # Create an in-memory store with mock data
        self.store = Store(db_path=":memory:")
        self.df_bank = pd.DataFrame([
            {"txn_id": "TXN_101", "date": "2026-03-01", "amount": 250.00, "counterparty": "GitHub", "description": "Enterprise Plan"},
            {"txn_id": "TXN_102", "date": "2026-03-01", "amount": 250.00, "counterparty": "GitHub", "description": "Enterprise Plan (Dup)"},
            {"txn_id": "TXN_103", "date": "2026-03-02", "amount": 999.00, "counterparty": "Unknown", "description": "Unmatched"}
        ])
        self.df_gl = pd.DataFrame([
            {"entry_id": "GL_101", "date": "2026-03-01", "amount": 250.00, "vendor_id": "GitHub Inc", "memo": "Dev tooling"}
        ])
        self.df_invoices = pd.DataFrame([
            {"invoice_id": "INV_501", "vendor_id": "GitHub Inc", "amount": 250.00, "date": "2026-03-01"}
        ])
        self.store.load_dataframes(self.df_bank, self.df_gl, self.df_invoices)
        self.server = FinanceMCPServer(store=self.store)

    def tearDown(self):
        self.store.close()

    def test_mcp_initialize(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 1)
        self.assertIn("capabilities", res["result"])
        self.assertEqual(res["result"]["serverInfo"]["name"], "finance-controller-auditor")

    def test_mcp_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        res = self.server.handle_request(req)
        self.assertEqual(res["id"], 2)
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("get_bank_transaction", tool_names)
        self.assertIn("check_duplicate_bank_txns", tool_names)
        self.assertIn("search_gl_by_amount", tool_names)
        self.assertIn("search_gl_by_vendor", tool_names)
        self.assertIn("search_invoices", tool_names)
        self.assertIn("audit_exception", tool_names)

    def test_mcp_tool_call_search_gl(self):
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_gl_by_amount",
                "arguments": {"amount": 250.00, "tolerance": 0.01}
            }
        }
        res = self.server.handle_request(req)
        self.assertFalse(res["result"]["isError"])
        content = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["entry_id"], "GL_101")

    def test_mcp_tool_call_audit_exception(self):
        # TXN_102 is duplicate of TXN_101
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "audit_exception",
                "arguments": {"txn_id": "TXN_102"}
            }
        }
        res = self.server.handle_request(req)
        self.assertFalse(res["result"]["isError"])
        content = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(content["status"], "DUPLICATE_FLAG")
        self.assertIn("TXN_101", content["reason"])

    def test_mcp_unknown_method(self):
        req = {"jsonrpc": "2.0", "id": 5, "method": "unknown_method", "params": {}}
        res = self.server.handle_request(req)
        self.assertIn("error", res)
        self.assertEqual(res["error"]["code"], -32601)

if __name__ == "__main__":
    unittest.main()
