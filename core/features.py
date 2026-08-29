import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from rapidfuzz import fuzz

def build_features(df_bank, df_gl, df_invoices):
    df_bank['date'] = pd.to_datetime(df_bank['date'])
    df_gl['date'] = pd.to_datetime(df_gl['date'])
    df_cross = df_bank.merge(df_gl, how='cross', suffixes=('_b', '_g'))
    
    date_diffs = (df_cross['date_b'] - df_cross['date_g']).dt.days.abs()
    amt_diff_pcts = (df_cross['amount_b'] - df_cross['amount_g']).abs() / np.maximum(df_cross['amount_b'], 0.01)
    
    mask = (date_diffs <= 3) & (amt_diff_pcts <= 0.05)
    df_candidates = df_cross[mask].copy().reset_index(drop=True)
    
    df_candidates = df_candidates.rename(columns={
        'amount_b': 'b_amount', 'amount_g': 'g_amount',
        'date_b': 'b_date', 'date_g': 'g_date',
        'description': 'b_desc', 'counterparty': 'b_counterparty',
        'memo': 'g_memo', 'vendor_id': 'g_vendor_id'
    })
    
    df_features = df_candidates[['txn_id', 'entry_id']].copy()
    df_features['amount_diff'] = (df_candidates['b_amount'] - df_candidates['g_amount']).abs()
    df_features['amount_ratio'] = np.minimum(df_candidates['b_amount'], df_candidates['g_amount']) / np.maximum(df_candidates['b_amount'], df_candidates['g_amount'])
    df_features['date_diff_days'] = (pd.to_datetime(df_candidates['b_date']) - pd.to_datetime(df_candidates['g_date'])).dt.days.abs()
    df_features['direction_match'] = 1
    
    all_text = pd.concat([df_bank['description'], df_gl['memo']]).unique()
    tfidf = TfidfVectorizer().fit(all_text)
    b_vecs = tfidf.transform(df_candidates['b_desc'].fillna(''))
    g_vecs = tfidf.transform(df_candidates['g_memo'].fillna(''))
    df_features['desc_cosine'] = np.asarray(b_vecs.multiply(g_vecs).sum(axis=1)).flatten()
    
    df_features['counterparty_fuzzy'] = [
        fuzz.ratio(str(b), str(g)) / 100.0 
        for b, g in zip(df_candidates['b_counterparty'], df_candidates['g_vendor_id'])
    ]
    
    merged_inv = df_candidates[['txn_id', 'entry_id', 'g_vendor_id', 'b_amount']].merge(
        df_invoices[['vendor_id', 'amount']], left_on='g_vendor_id', right_on='vendor_id', how='left'
    )
    valid_inv = merged_inv[(merged_inv['amount'] - merged_inv['b_amount']).abs() <= 2.0].drop_duplicates(subset=['txn_id', 'entry_id'])
    
    df_features = df_features.merge(valid_inv[['txn_id', 'entry_id', 'amount']], on=['txn_id', 'entry_id'], how='left')
    df_features['has_invoice'] = df_features['amount'].notna().astype(int)
    df_features['invoice_amount_diff'] = np.where(df_features['has_invoice'] == 1, (df_candidates['b_amount'] - df_features['amount']).abs(), -1.0)
    
    return df_features.drop(columns=['amount'])