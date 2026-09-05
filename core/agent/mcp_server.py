import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.store import Store
from core.agent.tools import AuditTools
from core.agent.exception_agent import resolve_exception

logger = logging.getLogger("finance-mcp-server")

# Default MCP Tool Definitions
MCP_TOOLS_MANIFEST = [
    {
        "name": "get_bank_transaction",
        "description": "Retrieve full details of a bank statement transaction by its txn_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "txn_id": {"type": "string", "description": "The bank transaction ID (e.g. TXN_001)."}
            },
            "required": ["txn_id"]
        }
    },
    {
        "name": "check_duplicate_bank_txns",
        "description": "Check if identical or near-identical bank transactions exist (same amount & counterparty).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "txn_id": {"type": "string", "description": "The transaction ID being inspected."},
                "counterparty": {"type": "string", "description": "The merchant or counterparty name."},
                "amount": {"type": "number", "description": "The monetary amount."}
            },
            "required": ["txn_id"]
        }
    },
    {
        "name": "search_gl_by_amount",
        "description": "Search General Ledger entries matching a target amount within a tolerance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "The target transaction amount."},
                "tolerance": {"type": "number", "description": "Allowed discrepancy (default 0.05).", "default": 0.05},
                "limit": {"type": "integer", "description": "Maximum records to return.", "default": 5}
            },
            "required": ["amount"]
        }
    },
    {
        "name": "search_gl_by_vendor",
        "description": "Fuzzy search General Ledger entries by vendor name or memo keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string", "description": "Vendor or merchant name to search."},
                "limit": {"type": "integer", "description": "Maximum records to return.", "default": 5}
            },
            "required": ["vendor_name"]
        }
    },
    {
        "name": "search_invoices",
        "description": "Search supplier/vendor invoices by vendor name and/or invoice amount.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vendor_name": {"type": "string", "description": "Vendor name in invoice."},
                "amount": {"type": "number", "description": "Invoice amount."},
                "tolerance": {"type": "number", "description": "Allowed discrepancy (default 0.05).", "default": 0.05}
            }
        }
    },
    {
        "name": "audit_exception",
        "description": "Execute the full Autonomous Exception Auditor on a bank transaction to determine verdict (DUPLICATE_FLAG, RESOLVED_WITH_CONFIDENCE, or NEEDS_HUMAN) with reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "txn_id": {"type": "string", "description": "The bank transaction ID to audit."}
            },
            "required": ["txn_id"]
        }
    }
]

class FinanceMCPServer:
    """
    Model Context Protocol (MCP) Server for the Finance Controller.
    Exposes financial ledger tools and autonomous audit capabilities over standard JSON-RPC stdio.
    """
    def __init__(self, store: Optional[Store] = None, db_path: Optional[str] = None):
        if store:
            self.store = store
        else:
            path = db_path or os.path.join(PROJECT_ROOT, "finance_controller.duckdb")
            self.store = Store(path if os.path.exists(path) else ":memory:")
            # If in-memory and data files exist, load them automatically
            data_dir = os.path.join(PROJECT_ROOT, "data")
            if self.store.conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'bank_txns'").fetchone()[0] == 0:
                try:
                    import pandas as pd
                    b_path = os.path.join(data_dir, "bank_statements.csv")
                    g_path = os.path.join(data_dir, "gl_ledger.csv")
                    i_path = os.path.join(data_dir, "invoices.csv")
                    if all(os.path.exists(p) for p in [b_path, g_path, i_path]):
                        self.store.load_dataframes(
                            pd.read_csv(b_path), pd.read_csv(g_path), pd.read_csv(i_path)
                        )
                except Exception as e:
                    logger.warning(f"Could not auto-load CSVs into Store: {e}")

        self.tools = AuditTools(self.store)

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool and return the output dictionary."""
        if tool_name == "get_bank_transaction":
            return self.tools.get_bank_transaction(arguments.get("txn_id", ""))
        elif tool_name == "check_duplicate_bank_txns":
            return self.tools.check_duplicate_bank_txns(
                txn_id=arguments.get("txn_id", ""),
                counterparty=arguments.get("counterparty"),
                amount=arguments.get("amount")
            )
        elif tool_name == "search_gl_by_amount":
            return self.tools.search_gl_by_amount(
                amount=float(arguments.get("amount", 0.0)),
                tolerance=float(arguments.get("tolerance", 0.05)),
                limit=int(arguments.get("limit", 5))
            )
        elif tool_name == "search_gl_by_vendor":
            return self.tools.search_gl_by_vendor(
                vendor_name=arguments.get("vendor_name", ""),
                limit=int(arguments.get("limit", 5))
            )
        elif tool_name == "search_invoices":
            amt = arguments.get("amount")
            return self.tools.search_invoices(
                vendor_name=arguments.get("vendor_name"),
                amount=float(amt) if amt is not None else None,
                tolerance=float(arguments.get("tolerance", 0.05))
            )
        elif tool_name == "audit_exception":
            t_id = arguments.get("txn_id", "")
            verdict, reason = resolve_exception(t_id, self.store)
            res = getattr(resolve_exception(t_id, self.store), "matched_entry_id", None)
            return {
                "txn_id": t_id,
                "status": verdict,
                "reason": reason,
                "matched_entry_id": res
            }
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request compliant with MCP stdio specification."""
        method = request.get("method")
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": "finance-controller-auditor",
                        "version": "1.0.0"
                    }
                }
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": MCP_TOOLS_MANIFEST
                }
            }
        elif method == "tools/call":
            params = request.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            try:
                output = self.execute_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, indent=2, default=str)
                            }
                        ],
                        "isError": False
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{name}': {str(e)}"
                            }
                        ],
                        "isError": True
                    }
                }
        else:
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found"
                    }
                }
            return None

    def run_stdio(self):
        """Run the MCP JSON-RPC server on standard input/output."""
        sys.stderr.write("Finance MCP Server listening on stdio (JSON-RPC 2.0)...\n")
        sys.stderr.flush()

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

def main():
    if "--test" in sys.argv:
        print("Running Finance MCP Server in self-test mode...")
        server = FinanceMCPServer()
        list_resp = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools_found = len(list_resp["result"]["tools"])
        print(f"Discovered {tools_found} MCP tools successfully.")
        sys.exit(0)

    server = FinanceMCPServer()
    server.run_stdio()

if __name__ == "__main__":
    main()
