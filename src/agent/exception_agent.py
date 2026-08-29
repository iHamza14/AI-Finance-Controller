import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
import json
from .tools import get_agent_tools

def resolve_exception(txn_id, store):
    """
    Spins up a native tool-calling agent loop to investigate a specific transaction exception.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "NEEDS_HUMAN", "No GROQ_API_KEY provided. Cannot run agent triage."

    # Get the transaction details to provide context
    txn_df = store.conn.execute(f"SELECT * FROM bank_txns WHERE txn_id = '{txn_id}'").df()
    if txn_df.empty:
        return "NEEDS_HUMAN", "Transaction not found in database."
        
    txn_details = txn_df.iloc[0].to_dict()
    
    llm = ChatOpenAI(
        model="openai/gpt-oss-20b",
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        temperature=0
    )
    tools = get_agent_tools(store)
    
    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(tools)
    
    system_prompt = f"""You are an expert AI Finance Controller.
Your job is to investigate a bank transaction that failed automated reconciliation.
You have access to tools to query the GL ledger and invoices.
Do not hallucinate data. If you cannot find a clear match, do not guess.

Transaction to investigate:
{json.dumps(txn_details, indent=2, default=str)}

Based on your investigation, you must decide on a status:
1. RESOLVED_WITH_CONFIDENCE: If you found the matching GL entry or invoice (e.g. slight name mismatch or 1-2 day date skew).
2. DUPLICATE_FLAG: If this looks like a duplicate bank transaction.
3. NEEDS_HUMAN: If no match can be found, or you are unsure (e.g., missing GL booking entirely).

Important: Return your final answer ONLY in JSON format matching this schema:
{{
    "status": "RESOLVED_WITH_CONFIDENCE" | "NEEDS_HUMAN" | "DUPLICATE_FLAG",
    "reason": "Explain your findings briefly"
}}
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="Investigate this transaction using your tools, and then output the JSON verdict.")
    ]
    
    try:
        # Simple agent loop (max 7 steps to prevent infinite loops)
        for _ in range(7):
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            # If the LLM didn't call any tools, it means it's done reasoning and gave a final answer
            if not response.tool_calls:
                break
                
            # Execute each tool call and append the result
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                selected_tool = next((t for t in tools if t.name == tool_name), None)
                if selected_tool:
                    tool_result = selected_tool.invoke(tool_args)
                    messages.append(ToolMessage(
                        tool_call_id=tool_call["id"], 
                        content=str(tool_result), 
                        name=tool_name
                    ))

        final_message = messages[-1].content
        
        # Try to parse JSON from the final message
        try:
            import re
            match = re.search(r'\{.*\}', final_message, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                parsed = json.loads(final_message)
            return parsed.get("status", "NEEDS_HUMAN"), parsed.get("reason", final_message)
        except json.JSONDecodeError:
            return "NEEDS_HUMAN", f"Agent failed to return valid JSON: {final_message}"
            
    except Exception as e:
        return "NEEDS_HUMAN", f"Agent error: {str(e)}"
