from .exception_agent import ExceptionAuditorAgent, resolve_exception, resolve_exceptions_batch

__all__ = [
    "ExceptionAuditorAgent",
    "resolve_exception",
    "resolve_exceptions_batch",
    "FinanceMCPServer"
]

def __getattr__(name: str):
    if name == "FinanceMCPServer":
        from .mcp_server import FinanceMCPServer
        return FinanceMCPServer
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
