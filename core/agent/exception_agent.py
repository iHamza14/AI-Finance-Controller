import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from rapidfuzz import fuzz

from .tools import AuditTools, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert AI Finance Controller & Exception Auditor.
Your responsibility is to autonomously audit unresolved bank transactions that were NOT matched by the automated ML model.

You have access to inspection tools that query DuckDB ledgers (GL entries, invoices, duplicate bank transactions).
Use these tools step-by-step to gather evidence before reaching your verdict.

Follow these audit rules strictly:
1. DUPLICATE CHECK:
   First, check if this bank transaction is an accidental duplicate by calling `check_duplicate_bank_txns`.
   If another identical or nearly identical transaction exists with the same counterparty and amount, verdict must be: DUPLICATE_FLAG.

2. GL & INVOICE RECONCILIATION:
   Search for matching GL entries using `search_gl_by_amount` or `search_gl_by_vendor`.
   Cross-reference with `search_invoices` if helpful.
   - If you find a clear, single GL entry with matching/approximate amount and confirmed vendor/counterparty:
     Verdict must be: RESOLVED_WITH_CONFIDENCE (and you MUST supply the matching entry_id).
   - If there is an amount mismatch, missing GL entry, multiple conflicting entries, or missing documentation:
     Verdict must be: NEEDS_HUMAN.

3. FINAL OUTPUT:
   When you have sufficient evidence, output a clean JSON object (no markdown, no backticks, just valid JSON):
   {
     "status": "RESOLVED_WITH_CONFIDENCE" | "DUPLICATE_FLAG" | "NEEDS_HUMAN",
     "matched_entry_id": "<entry_id or null>",
     "reason": "<Detailed concise auditor explanation of why this verdict was reached and what evidence was used>"
   }
"""

class ExceptionAuditorAgent:
    """
    Autonomous tool-calling agent for auditing financial exceptions.
    Supports LLM tool-calling (Gemini / OpenAI) with deterministic heuristic fallback.
    """
    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        load_dotenv()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name or os.getenv("LLM_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"
        self.base_url = os.getenv("LLM_BASE_URL")
        
        # Default to Google's OpenAI-compatible endpoint if using GEMINI_API_KEY
        if self.api_key and not self.base_url and os.getenv("GEMINI_API_KEY"):
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            if not model_name and not os.getenv("GEMINI_MODEL"):
                self.model_name = "gemini-3.6-flash"

        self.llm = None
        if self.api_key:
            try:
                self.llm = ChatOpenAI(
                    model=self.model_name,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    temperature=0.0,
                    max_retries=2
                )
            except Exception as e:
                logger.warning(f"Failed to initialize ChatOpenAI: {e}. Will use heuristic fallback.")

    def _execute_tool(self, tools: AuditTools, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Route tool invocation to AuditTools."""
        if tool_name == "check_duplicate_bank_txns":
            return tools.check_duplicate_bank_txns(
                txn_id=arguments.get("txn_id", ""),
                counterparty=arguments.get("counterparty"),
                amount=arguments.get("amount")
            )
        elif tool_name == "search_gl_by_amount":
            return tools.search_gl_by_amount(
                amount=float(arguments.get("amount", 0.0)),
                tolerance=float(arguments.get("tolerance", 0.05))
            )
        elif tool_name == "search_gl_by_vendor":
            return tools.search_gl_by_vendor(
                vendor_name=arguments.get("vendor_name", "")
            )
        elif tool_name == "search_invoices":
            amt = arguments.get("amount")
            return tools.search_invoices(
                vendor_name=arguments.get("vendor_name"),
                amount=float(amt) if amt is not None else None,
                tolerance=float(arguments.get("tolerance", 0.05))
            )
        else:
            return {"error": f"Unknown tool '{tool_name}'"}

    def _heuristic_audit(self, txn_info: Dict[str, Any], tools: AuditTools) -> Dict[str, Any]:
        """
        Deterministic, rule-based fallback auditor when LLM is unavailable.
        Uses exact tolerances and fuzzy matching to accurately triage exceptions.
        """
        txn_id = txn_info.get("txn_id", "")
        amount = float(txn_info.get("amount", 0.0))
        counterparty = str(txn_info.get("counterparty", ""))

        # 1. Check for duplicate bank transactions
        duplicates = tools.check_duplicate_bank_txns(txn_id, counterparty=counterparty, amount=amount)
        if duplicates:
            dup_ids = [d["txn_id"] for d in duplicates]
            return {
                "status": "DUPLICATE_FLAG",
                "matched_entry_id": None,
                "reason": f"Identified {len(duplicates)} matching bank transaction(s) with identical amount (${amount:.2f}) and counterparty '{counterparty}' (IDs: {', '.join(dup_ids)})."
            }

        # 2. Search GL by amount
        gl_amount_matches = tools.search_gl_by_amount(amount, tolerance=0.05)
        for gl in gl_amount_matches:
            v_id = str(gl.get("vendor_id", ""))
            memo = str(gl.get("memo", ""))
            sim_v = fuzz.ratio(counterparty.lower(), v_id.lower())
            sim_m = fuzz.partial_ratio(counterparty.lower(), memo.lower())
            if max(sim_v, sim_m) >= 70:
                return {
                    "status": "RESOLVED_WITH_CONFIDENCE",
                    "matched_entry_id": gl["entry_id"],
                    "reason": f"Matched GL entry '{gl['entry_id']}' with exact amount (${amount:.2f}) and confirmed counterparty similarity ({max(sim_v, sim_m)}%)."
                }

        # 3. Search GL by vendor
        gl_vendor_matches = tools.search_gl_by_vendor(counterparty)
        for gl in gl_vendor_matches:
            gl_amt = float(gl.get("amount", 0.0))
            if abs(gl_amt - amount) <= 0.05:
                return {
                    "status": "RESOLVED_WITH_CONFIDENCE",
                    "matched_entry_id": gl["entry_id"],
                    "reason": f"Matched GL entry '{gl['entry_id']}' via vendor lookup for '{counterparty}' with matching amount (${amount:.2f})."
                }

        # 4. Search Invoices
        inv_matches = tools.search_invoices(vendor_name=counterparty, amount=amount, tolerance=0.05)
        if inv_matches:
            # We found an invoice, but if GL entry is missing, human review is needed
            inv_id = inv_matches[0].get("invoice_id", "Unknown")
            return {
                "status": "NEEDS_HUMAN",
                "matched_entry_id": None,
                "reason": f"Invoice {inv_id} found for ${amount:.2f}, but corresponding GL entry is missing or ambiguous."
            }

        # 5. Default unresolved exception
        return {
            "status": "NEEDS_HUMAN",
            "matched_entry_id": None,
            "reason": f"No matching GL entry or invoice found for counterparty '{counterparty}' and amount ${amount:.2f}."
        }

    def audit_transaction(self, txn_id: str, store) -> Dict[str, Any]:
        """
        Audits a single bank transaction exception using the tool-calling loop or fallback.
        """
        tools = AuditTools(store)
        txn_info = tools.get_bank_transaction(txn_id)
        if "error" in txn_info:
            return {
                "status": "NEEDS_HUMAN",
                "matched_entry_id": None,
                "reason": f"Transaction not found in ledger: {txn_info.get('error')}"
            }

        # If LLM is not configured, directly run heuristic audit
        if not self.llm:
            return self._heuristic_audit(txn_info, tools)

        # Autonomous ReAct Tool-Calling Loop
        try:
            llm_with_tools = self.llm.bind_tools(TOOL_DEFINITIONS)
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Audit this unmatched bank transaction:\n"
                        f"- Transaction ID: {txn_info.get('txn_id')}\n"
                        f"- Date: {txn_info.get('date')}\n"
                        f"- Amount: ${txn_info.get('amount')}\n"
                        f"- Counterparty: {txn_info.get('counterparty')}\n"
                        f"- Description: {txn_info.get('description', '')}\n\n"
                        f"Investigate using the available tools and determine the resolution."
                    )
                )
            ]

            max_steps = 4
            final_content = ""

            for step in range(max_steps):
                ai_msg: AIMessage = llm_with_tools.invoke(messages)
                messages.append(ai_msg)

                # If no tool calls, model is ready with final verdict
                if not ai_msg.tool_calls:
                    final_content = ai_msg.content
                    break

                # Execute requested tools
                for tc in ai_msg.tool_calls:
                    t_name = tc.get("name")
                    t_args = tc.get("args") or {}
                    t_id = tc.get("id", f"call_{step}")
                    
                    logger.info(f"Agent invoking tool '{t_name}' with args {t_args}")
                    tool_result = self._execute_tool(tools, t_name, t_args)
                    
                    messages.append(
                        ToolMessage(
                            tool_call_id=t_id,
                            name=t_name,
                            content=json.dumps(tool_result, default=str)
                        )
                    )

            # Parse JSON decision from final_content
            parsed = self._extract_json(final_content)
            if parsed and parsed.get("status") in ["RESOLVED_WITH_CONFIDENCE", "DUPLICATE_FLAG", "NEEDS_HUMAN"]:
                return parsed

            # Fallback if LLM output was malformed
            logger.warning("LLM response did not contain expected verdict format; running heuristic fallback.")
            return self._heuristic_audit(txn_info, tools)

        except Exception as e:
            logger.error(f"Error in LLM tool-calling loop for {txn_id}: {e}. Using heuristic fallback.")
            return self._heuristic_audit(txn_info, tools)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from text."""
        if not text:
            return None
        match = re.search(r'\{[^{}]*"status"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        try:
            return json.loads(text)
        except Exception:
            return None


class AuditVerdict(tuple):
    """
    A 2-tuple (verdict, reason) with additional attributes:
    - verdict: str
    - reason: str
    - matched_entry_id: Optional[str]
    Unpacks seamlessly into `verdict, reason = resolve_exception(...)`.
    """
    def __new__(cls, verdict: str, reason: str, matched_entry_id: Optional[str] = None):
        obj = super().__new__(cls, (verdict, reason))
        obj.verdict = verdict
        obj.reason = reason
        obj.matched_entry_id = matched_entry_id
        return obj


def resolve_exception(txn_id: str, store) -> AuditVerdict:
    """
    Public entrypoint for resolving a single exception.
    Compatible with `from core.agent.exception_agent import resolve_exception`.
    Unpacks as `verdict, reason = resolve_exception(...)`.
    Has `.matched_entry_id` attribute for downstream linking.
    """
    agent = ExceptionAuditorAgent()
    result = agent.audit_transaction(txn_id, store)
    return AuditVerdict(
        result.get("status", "NEEDS_HUMAN"),
        result.get("reason", "Audited by exception agent."),
        result.get("matched_entry_id")
    )



def resolve_exceptions_batch(
    exception_records: List[Dict[str, Any]], store, max_workers: int = 4
) -> List[Dict[str, Any]]:
    """
    Batch resolve a list of exception records.
    Chunks them into batches of 30 and pauses 5 seconds between API calls to avoid rate limits.
    """
    import time
    if not exception_records:
        return []

    agent = ExceptionAuditorAgent()
    results = []
    
    # We will process them sequentially to control the exact rate limit, 
    # but chunk them to reduce API calls if we had a batch prompt.
    # Since the agent currently processes 1 by 1 accurately with tools, 
    # and the user wants a 4-5s delay between chunks of 30, we can run 30 concurrently, 
    # then sleep 5s, then run 30.
    
    batch_size = 15 # Let's use 15 since Gemini free tier is 15 RPM!
    
    def _worker(rec):
        t_id = rec["txn_id"]
        res = agent.audit_transaction(t_id, store)
        rec_copy = dict(rec)
        rec_copy["agent_verdict"] = res.get("status", "NEEDS_HUMAN")
        rec_copy["reason"] = res.get("reason", "No reason provided")
        rec_copy["matched_entry_id"] = res.get("matched_entry_id")
        return rec_copy

    for i in range(0, len(exception_records), batch_size):
        chunk = exception_records[i:i+batch_size]
        
        logger.info(f"Processing chunk of {len(chunk)} exceptions to avoid rate limits...")
        
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_to_rec = {executor.submit(_worker, r): r for r in chunk}
            for future in as_completed(future_to_rec):
                try:
                    results.append(future.result())
                except Exception as e:
                    orig = future_to_rec[future]
                    orig_copy = dict(orig)
                    orig_copy["agent_verdict"] = "ERROR"
                    orig_copy["reason"] = f"Worker failed: {str(e)}"
                    orig_copy["matched_entry_id"] = None
                    results.append(orig_copy)
                    
        # Sleep 5 seconds between chunks to respect the rate limits!
        if i + batch_size < len(exception_records):
            logger.info("Sleeping 5 seconds to respect Gemini API rate limits...")
            time.sleep(5)

    # Maintain original order
    txn_order = {rec["txn_id"]: idx for idx, rec in enumerate(exception_records)}
    results.sort(key=lambda x: txn_order.get(x["txn_id"], 0))
    return results
