import pandas as pd
import numpy as np
from faker import Faker
from datetime import timedelta
import os
import uuid
import random

# Initialize Faker with seed for reproducibility
fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

def generate_dataset(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # Target counts
    total_bank_txns = 60
    
    # Anomaly distribution based on design doc
    dist = {
        "clean_match": int(total_bank_txns * 0.60),       # 36
        "amount_mismatch": int(total_bank_txns * 0.12),   # 7
        "date_skew": int(total_bank_txns * 0.10),         # 6
        "missing_gl": int(total_bank_txns * 0.08),        # 5
        "duplicate_bank": int(total_bank_txns * 0.05),    # 3
        "vendor_mismatch": int(total_bank_txns * 0.05)    # 3
    }
    
    # Adjust for rounding to hit exactly 60
    total_assigned = sum(dist.values())
    dist["clean_match"] += (total_bank_txns - total_assigned)

    bank_records = []
    gl_records = []
    invoice_records = []
    ground_truth = []
    
    start_date = fake.date_between(start_date="-30d", end_date="today")
    
    # We will generate base transactions and modify them based on anomaly type
    
    # 1. Generate Clean Matches
    for _ in range(dist["clean_match"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        amount = round(random.uniform(50.0, 5000.0), 2)
        vendor_name = fake.company()
        vendor_id = f"V_{fake.unique.random_number(digits=4)}"
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        inv_id = f"INV_{uuid.uuid4().hex[:8].upper()}"
        
        # Bank
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": amount, "direction": "DR", 
            "description": f"POS Debit {vendor_name}", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        # GL
        gl_records.append({
            "entry_id": gl_id, "date": date, "amount": amount, "account_code": "5000-EXP",
            "memo": f"Payment to {vendor_name}", "vendor_id": vendor_id, "journal_ref": fake.bban(), "created_by": "system"
        })
        # Invoice
        invoice_records.append({
            "invoice_id": inv_id, "date": date - timedelta(days=random.randint(1, 15)), 
            "amount": amount, "vendor_id": vendor_id, "vendor_name": vendor_name, 
            "status": "PAID", "po_number": f"PO_{fake.random_number(digits=5)}"
        })
        
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": gl_id, "match_label": 1, "anomaly": "none"})

    # 2. Amount Mismatch (bank fee / rounding)
    for _ in range(dist["amount_mismatch"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        amount = round(random.uniform(50.0, 5000.0), 2)
        bank_amount = amount + round(random.uniform(-2.0, 2.0), 2)  # Diff of -2.00 to 2.00
        vendor_name = fake.company()
        vendor_id = f"V_{fake.unique.random_number(digits=4)}"
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": bank_amount, "direction": "DR", 
            "description": f"Wire {vendor_name}", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        gl_records.append({
            "entry_id": gl_id, "date": date, "amount": amount, "account_code": "5000-EXP",
            "memo": f"Payment {vendor_name}", "vendor_id": vendor_id, "journal_ref": fake.bban(), "created_by": "system"
        })
        
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": gl_id, "match_label": 1, "anomaly": "amount_mismatch"})

    # 3. Date Skew (GL books T+1 or T+2)
    for _ in range(dist["date_skew"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        gl_date = date + timedelta(days=random.randint(1, 2))
        amount = round(random.uniform(50.0, 5000.0), 2)
        vendor_name = fake.company()
        vendor_id = f"V_{fake.unique.random_number(digits=4)}"
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": amount, "direction": "DR", 
            "description": f"ACH {vendor_name}", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        gl_records.append({
            "entry_id": gl_id, "date": gl_date, "amount": amount, "account_code": "5000-EXP",
            "memo": f"Paid {vendor_name}", "vendor_id": vendor_id, "journal_ref": fake.bban(), "created_by": "system"
        })
        
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": gl_id, "match_label": 1, "anomaly": "date_skew"})

    # 4. Missing GL Entry
    for _ in range(dist["missing_gl"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        amount = round(random.uniform(50.0, 5000.0), 2)
        vendor_name = fake.company()
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": amount, "direction": "DR", 
            "description": f"Debit {vendor_name}", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        # No GL record
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": None, "match_label": 0, "anomaly": "missing_gl"})

    # 5. Duplicate Bank Txn (Same amount+counterparty, 1-day apart)
    for _ in range(dist["duplicate_bank"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        amount = round(random.uniform(50.0, 5000.0), 2)
        vendor_name = fake.company()
        vendor_id = f"V_{fake.unique.random_number(digits=4)}"
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        bank_id_dup = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": amount, "direction": "DR", 
            "description": f"Auth {vendor_name}", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        bank_records.append({
            "txn_id": bank_id_dup, "date": date + timedelta(days=1), "amount": amount, "direction": "DR", 
            "description": f"Auth {vendor_name} (Dup)", "counterparty": vendor_name, "bank_ref": fake.bban()
        })
        
        gl_records.append({
            "entry_id": gl_id, "date": date, "amount": amount, "account_code": "5000-EXP",
            "memo": f"Expense {vendor_name}", "vendor_id": vendor_id, "journal_ref": fake.bban(), "created_by": "system"
        })
        
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": gl_id, "match_label": 1, "anomaly": "none"})
        ground_truth.append({"bank_txn_id": bank_id_dup, "gl_entry_id": None, "match_label": 0, "anomaly": "duplicate_bank"})

    # 6. Vendor Name Mismatch
    for _ in range(dist["vendor_mismatch"]):
        date = fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30))
        amount = round(random.uniform(50.0, 5000.0), 2)
        vendor_name_bank = "ACME Corp"
        vendor_name_gl = "Acme Corporation"
        vendor_id = f"V_{fake.unique.random_number(digits=4)}"
        
        bank_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        
        bank_records.append({
            "txn_id": bank_id, "date": date, "amount": amount, "direction": "DR", 
            "description": f"Payment to {vendor_name_bank}", "counterparty": vendor_name_bank, "bank_ref": fake.bban()
        })
        gl_records.append({
            "entry_id": gl_id, "date": date, "amount": amount, "account_code": "5000-EXP",
            "memo": f"Vendor: {vendor_name_gl}", "vendor_id": vendor_id, "journal_ref": fake.bban(), "created_by": "system"
        })
        
        ground_truth.append({"bank_txn_id": bank_id, "gl_entry_id": gl_id, "match_label": 1, "anomaly": "vendor_mismatch"})

    # Add extra orphan GL entries (to reach 65 rows as per design doc)
    extra_gl_needed = 65 - len(gl_records)
    for _ in range(max(0, extra_gl_needed)):
        gl_id = f"GL_{uuid.uuid4().hex[:8].upper()}"
        gl_records.append({
            "entry_id": gl_id, "date": fake.date_between_dates(date_start=start_date, date_end=start_date + timedelta(days=30)), 
            "amount": round(random.uniform(50.0, 5000.0), 2), "account_code": "5000-EXP",
            "memo": "Orphan GL Entry", "vendor_id": f"V_{fake.random_number(digits=4)}", "journal_ref": fake.bban(), "created_by": "human"
        })

    # Shuffle data
    random.shuffle(bank_records)
    random.shuffle(gl_records)
    random.shuffle(invoice_records)

    # Save to CSV
    pd.DataFrame(bank_records).to_csv(os.path.join(output_dir, "bank_statements.csv"), index=False)
    pd.DataFrame(gl_records).to_csv(os.path.join(output_dir, "gl_ledger.csv"), index=False)
    pd.DataFrame(invoice_records).to_csv(os.path.join(output_dir, "invoices.csv"), index=False)
    pd.DataFrame(ground_truth).to_csv(os.path.join(output_dir, "ground_truth.csv"), index=False)
    
    print(f"Generated {len(bank_records)} bank records, {len(gl_records)} GL records, and {len(invoice_records)} invoices.")
    print(f"Data saved to {output_dir}")

if __name__ == "__main__":
    generate_dataset("data")
