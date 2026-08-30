import pandas as pd

# Load data
df_gt = pd.read_csv('ground_truth.csv')
df_res = pd.read_csv('data/6f1b861e-2d68-403c-8803-abf9154eda35/final_results.csv')

# Merge on txn_id
df = pd.merge(df_gt, df_res, on='txn_id', how='left')

# ML Evaluation
# The ML model handles things marked as 'MATCHED'
ml_mask = df['status'] == 'MATCHED'
df_ml = df[ml_mask]

# ML is correct if match_label == 1 AND entry_id (from res) == entry_id (from gt)
ml_correct = ((df_ml['match_label'] == 1) & (df_ml['entry_id_x'] == df_ml['entry_id_y'])).sum()
ml_total = len(df_ml)
ml_accuracy = ml_correct / ml_total if ml_total > 0 else 0

# Agent Evaluation
# The Agent handles everything NOT marked as 'MATCHED'
agent_mask = df['status'] != 'MATCHED'
df_agent = df[agent_mask]

agent_correct = 0
agent_details = {"duplicate_correct": 0, "needs_human_correct": 0, "resolved_correct": 0, "total_agent": len(df_agent)}

for _, row in df_agent.iterrows():
    anomaly = row['anomaly_type']
    status = row['status']
    
    if anomaly == 'duplicate_bank' and status == 'DUPLICATE_FLAG':
        agent_correct += 1
        agent_details['duplicate_correct'] += 1
    elif anomaly in ['amount_mismatch', 'missing_gl'] and status == 'NEEDS_HUMAN':
        agent_correct += 1
        agent_details['needs_human_correct'] += 1
    elif row['match_label'] == 1 and status == 'RESOLVED_WITH_CONFIDENCE':
        agent_correct += 1
        agent_details['resolved_correct'] += 1

agent_accuracy = agent_correct / len(df_agent) if len(df_agent) > 0 else 0

# Overall Accuracy
total_correct = ml_correct + agent_correct
total_rows = len(df)
overall_accuracy = total_correct / total_rows if total_rows > 0 else 0

print(f"Overall Accuracy: {overall_accuracy * 100:.2f}% ({total_correct}/{total_rows})")
print(f"ML Model Accuracy: {ml_accuracy * 100:.2f}% ({ml_correct}/{ml_total})")
print(f"Agent Accuracy: {agent_accuracy * 100:.2f}% ({agent_correct}/{len(df_agent)})")
print("Agent Breakdown:", agent_details)
