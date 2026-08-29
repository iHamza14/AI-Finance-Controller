import pandas as pd
import numpy as np
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def generate_candidate_pairs(bank_df, gl_df):
    """
    Generate candidate pairs by blocking on date +/- 3 days and amount +/- 5%.
    """
    # Cross join everything (inefficient for large datasets, but fine for 60x65 = 3900 pairs)
    bank_df['key'] = 1
    gl_df['key'] = 1
    
    pairs = pd.merge(bank_df, gl_df, on='key', suffixes=('_bank', '_gl')).drop('key', axis=1)
    
    # Block on date
    date_diff = (pairs['date_bank'] - pairs['date_gl']).dt.days.abs()
    pairs = pairs[date_diff <= 3]
    
    # Block on amount
    amt_diff_pct = (pairs['amount_bank'] - pairs['amount_gl']).abs() / pairs['amount_bank']
    pairs = pairs[amt_diff_pct <= 0.05]
    
    return pairs

def compute_features(pairs_df, invoice_df):
    """
    Compute the 8 features for each candidate pair.
    """
    if pairs_df.empty:
        return pd.DataFrame()
        
    features = pd.DataFrame(index=pairs_df.index)
    
    features['txn_id'] = pairs_df['txn_id']
    features['entry_id'] = pairs_df['entry_id']
    
    # 1. amount_diff
    features['amount_diff'] = (pairs_df['amount_bank'] - pairs_df['amount_gl']).abs()
    
    # 2. amount_ratio
    min_amt = np.minimum(pairs_df['amount_bank'], pairs_df['amount_gl'])
    max_amt = np.maximum(pairs_df['amount_bank'], pairs_df['amount_gl'])
    features['amount_ratio'] = min_amt / max_amt
    
    # 3. date_diff_days
    features['date_diff_days'] = (pairs_df['date_bank'] - pairs_df['date_gl']).dt.days.abs()
    
    # 4. desc_cosine
    tfidf = TfidfVectorizer()
    # Fill nan with empty string
    desc_bank = pairs_df['description'].fillna("")
    memo_gl = pairs_df['memo'].fillna("")
    
    # We compute similarity row by row. (For large data, vectorize better)
    def compute_sim(row):
        try:
            vecs = tfidf.fit_transform([row['desc_bank'], row['memo_gl']])
            return cosine_similarity(vecs[0], vecs[1])[0][0]
        except ValueError:
            return 0.0
            
    sim_df = pd.DataFrame({'desc_bank': desc_bank, 'memo_gl': memo_gl})
    features['desc_cosine'] = sim_df.apply(compute_sim, axis=1)
    
    # 5. counterparty_fuzzy
    def fuzzy_match(row):
        return fuzz.ratio(str(row['counterparty']).lower(), str(row['vendor_id_gl']).lower())
    
    # To properly check vendor names from GL, we need to join with invoice/vendor master 
    # but here vendor_id is in GL. Let's just fuzzy match counterparty against memo/vendor_id for now
    features['counterparty_fuzzy'] = pairs_df.apply(
        lambda r: fuzz.ratio(str(r['counterparty']).lower(), str(r['memo']).lower()), axis=1
    )
    
    # 6. direction_match
    # Assuming DR maps to expense codes containing 'EXP'
    features['direction_match'] = ((pairs_df['direction'] == 'DR') & (pairs_df['account_code'].str.contains('EXP'))).astype(int)
    
    # 7 & 8. has_invoice & invoice_amount_diff
    # We check if an invoice exists for the gl's vendor_id and similar amount
    def check_invoice(row):
        vendor_id = row['vendor_id']
        amt = row['amount_bank']
        
        # Look up invoice
        inv = invoice_df[(invoice_df['vendor_id'] == vendor_id)]
        if not inv.empty:
            # Find closest amount
            closest_inv = inv.iloc[(inv['amount'] - amt).abs().argmin()]
            diff = abs(amt - closest_inv['amount'])
            if diff <= (amt * 0.05): # within 5%
                return pd.Series([1, diff])
        return pd.Series([0, -1.0])
        
    inv_feats = pairs_df.apply(check_invoice, axis=1)
    features['has_invoice'] = inv_feats[0]
    features['invoice_amount_diff'] = inv_feats[1]
    
    return features
