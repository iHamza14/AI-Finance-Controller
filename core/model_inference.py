import joblib
import pandas as pd

FEATURE_COLS = [
    'amount_diff', 'amount_ratio', 'date_diff_days', 
    'desc_cosine', 'counterparty_fuzzy', 'direction_match', 
    'has_invoice', 'invoice_amount_diff'
]

def load_model(model_path):
    return joblib.load(model_path)

def predict_and_route(df_features, model, threshold=0.85):
    if df_features.empty:
        return [], pd.DataFrame()
        
    df_features['match_prob'] = model.predict_proba(df_features[FEATURE_COLS])[:, 1]
    
    df_high_conf = df_features[df_features['match_prob'] >= threshold].copy()
    
    match_counts = df_high_conf['txn_id'].value_counts()
    safe_txn_ids = match_counts[match_counts == 1].index
    
    df_safe_matches = df_high_conf[df_high_conf['txn_id'].isin(safe_txn_ids)].copy()
    confirmed_pairs = df_safe_matches[['txn_id', 'entry_id']].to_dict('records')
    
    return confirmed_pairs, df_safe_matches