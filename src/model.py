import pandas as pd
import numpy as np

class DummyModel:
    """
    A placeholder model until the real ML model is integrated.
    It returns high probability for matches with 0 amount difference and small date difference,
    and low probability otherwise.
    """
    def __init__(self):
        self.threshold = 0.75

    def predict_proba(self, features_df):
        """
        Returns a DataFrame with txn_id, entry_id, and match_score
        """
        results = []
        
        feature_cols = [
            'amount_diff', 'amount_ratio', 'date_diff_days', 'desc_cosine', 
            'counterparty_fuzzy', 'direction_match', 'has_invoice', 'invoice_amount_diff'
        ]
        
        for idx, row in features_df.iterrows():
            score = 0.0
            
            # Simple heuristic mimicking a model
            if row['amount_diff'] < 0.05:
                score += 0.4
            if row['date_diff_days'] <= 1:
                score += 0.3
            if row['desc_cosine'] > 0.5:
                score += 0.1
            if row['has_invoice'] == 1:
                score += 0.2
                
            # Cap at 0.99
            score = min(score, 0.99)
            
            results.append({
                'txn_id': row['txn_id'],
                'entry_id': row['entry_id'],
                'match_score': score
            })
            
        return pd.DataFrame(results)
