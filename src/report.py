import json
import os
from jinja2 import Template
import uuid
from datetime import datetime

def generate_report(store, ml_metrics, output_dir="outputs"):
    os.makedirs(output_dir, exist_ok=True)
    
    # Calculate stats
    total_bank_txns = store.conn.execute("SELECT COUNT(*) FROM bank_txns").fetchone()[0]
    total_matches = store.conn.execute("SELECT COUNT(*) FROM match_results").fetchone()[0]
    exceptions = store.get_exception_summary()
    total_exceptions = len(exceptions)
    
    resolved_by_agent = sum(1 for e in exceptions if e['agent_verdict'] == 'RESOLVED_WITH_CONFIDENCE')
    
    match_rate = total_matches / total_bank_txns if total_bank_txns else 0
    exception_rate = total_exceptions / total_bank_txns if total_bank_txns else 0
    agent_res_rate = resolved_by_agent / total_exceptions if total_exceptions else 0
    
    report_data = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "batch_size": total_bank_txns,
        "match_rate": round(match_rate, 3),
        "exception_rate": round(exception_rate, 3),
        "agent_resolution_rate": round(agent_res_rate, 3),
        "ml_metrics": ml_metrics,
        "exceptions": exceptions
    }
    
    # 1. Write JSON
    with open(os.path.join(output_dir, "reconciliation_report.json"), "w") as f:
        json.dump(report_data, f, indent=2)
        
    # 2. Write HTML
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Finance Controller - Reconciliation Report</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 1000px; margin: 0 auto; background-color: #f8f9fa; color: #333; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .summary-cards { display: flex; gap: 20px; margin-bottom: 30px; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); flex: 1; text-align: center; }
            .card h3 { margin-top: 0; color: #7f8c8d; font-size: 0.9em; text-transform: uppercase; }
            .card .value { font-size: 2em; font-weight: bold; color: #2980b9; }
            table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #34495e; color: white; font-weight: 500; }
            tr:hover { background-color: #f5f5f5; }
            .verdict-RESOLVED_WITH_CONFIDENCE { color: #27ae60; font-weight: bold; }
            .verdict-NEEDS_HUMAN { color: #e74c3c; font-weight: bold; }
            .verdict-DUPLICATE_FLAG { color: #f39c12; font-weight: bold; }
            .section { margin-bottom: 40px; }
        </style>
    </head>
    <body>
        <h1>Reconciliation Report</h1>
        <p><strong>Run ID:</strong> {{ run_id }} | <strong>Timestamp:</strong> {{ timestamp }}</p>
        
        <div class="summary-cards">
            <div class="card">
                <h3>Batch Size</h3>
                <div class="value">{{ batch_size }}</div>
            </div>
            <div class="card">
                <h3>Match Rate</h3>
                <div class="value">{{ (match_rate * 100)|round(1) }}%</div>
            </div>
            <div class="card">
                <h3>Exception Rate</h3>
                <div class="value">{{ (exception_rate * 100)|round(1) }}%</div>
            </div>
            <div class="card">
                <h3>Agent Resolution</h3>
                <div class="value">{{ (agent_resolution_rate * 100)|round(1) }}%</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Exceptions ({{ exceptions|length }})</h2>
            <table>
                <tr>
                    <th>Txn ID</th>
                    <th>Counterparty</th>
                    <th>Amount</th>
                    <th>Agent Verdict</th>
                    <th>Reasoning</th>
                </tr>
                {% for exc in exceptions %}
                <tr>
                    <td>{{ exc.txn_id }}</td>
                    <td>{{ exc.counterparty }}</td>
                    <td>${{ "%.2f"|format(exc.amount) }}</td>
                    <td class="verdict-{{ exc.agent_verdict }}">{{ exc.agent_verdict }}</td>
                    <td><small>{{ exc.reason }}</small></td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    html_output = template.render(**report_data)
    
    with open(os.path.join(output_dir, "reconciliation_report.html"), "w") as f:
        f.write(html_output)
        
    print(f"Reports generated in {output_dir}")
