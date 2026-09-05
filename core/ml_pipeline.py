from core.features import build_features
from core.model_inference import load_model, predict_and_route

def run_ml_core(df_bank, df_gl, df_invoices, model_path="./model.pkl"):
    df_features = build_features(df_bank, df_gl, df_invoices)
    
    model = load_model(model_path)
    
    confirmed_pairs, df_safe_matches = predict_and_route(df_features, model, threshold=0.90)
    
    matched_txn_ids = df_safe_matches['txn_id'].unique().tolist() if not df_safe_matches.empty else []
    df_exceptions = df_bank[~df_bank['txn_id'].isin(matched_txn_ids)].copy()
    
    return confirmed_pairs, df_exceptions