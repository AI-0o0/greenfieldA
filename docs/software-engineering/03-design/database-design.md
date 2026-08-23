# 04. Target Database Design

## 1. Schema Enhancements & Normalization
The target database schema extends the relational model to support complete auditability, precise geographic buffer attributes, and incident resolution:

### Enhanced / New Columns:
1. **`Fields` Table**: Added `canal_distance_meters REAL` and `is_organic_border BOOLEAN` to enable direct SQL buffer queries instead of text parsing.
2. **`Chemicals` Table**: Added `min_canal_buffer_m REAL`, `min_organic_buffer_m REAL`, and `max_wind_speed_kmh REAL` to parameterize all regulatory checks in data.
3. **`Equipment` Table**: Added `operating_hours REAL` and `last_calibrated_at DATETIME`.
4. **`Incident_Notes` Table**: Added `dispatch_id FK` and `resolved_at DATETIME`.
5. **`Audit_Logs` Table (NEW)**:
   - `audit_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `actor_type TEXT NOT NULL`
   - `actor_id INTEGER NOT NULL`
   - `action_name TEXT NOT NULL`
   - `payload_json TEXT NOT NULL`
   - `status TEXT NOT NULL`
   - `timestamp DATETIME DEFAULT CURRENT_TIMESTAMP`
6. **`Financing_Applications` Table (NEW)**:
   - `application_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `customer_id INTEGER NOT NULL REFERENCES Customers(customer_id)`
   - `field_id INTEGER REFERENCES Fields(field_id)`
   - `requested_amount REAL NOT NULL CHECK (requested_amount > 0)`
   - `purpose TEXT NOT NULL`
   - `status TEXT NOT NULL CHECK (status IN ('draft', 'pending_eligibility', 'pending_documents', 'under_review', 'submitted', 'approved', 'rejected', 'cancelled'))`
   - `admin_approved_by INTEGER REFERENCES Technicians(technician_id)`
   - `provider_reference TEXT`
   - `interest_rate REAL`
   - `term_months INTEGER`
   - `monthly_payment REAL`
   - `farmer_accepted BOOLEAN`
   - `rejection_reason TEXT`
   - `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`
   - `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP`
7. **`Financial_Transactions` Table (NEW)**:
   - `transaction_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `application_id INTEGER NOT NULL REFERENCES Financing_Applications(application_id)`
   - `customer_id INTEGER NOT NULL REFERENCES Customers(customer_id)`
   - `transaction_type TEXT NOT NULL CHECK (transaction_type IN ('disbursement', 'repayment', 'fee', 'adjustment'))`
   - `amount REAL NOT NULL CHECK (amount > 0)`
   - `status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'reversed'))`
   - `verification_hash TEXT NOT NULL`
   - `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`

---

## 2. Migration & Indexing Strategy
- **Migration Framework**: Integrate **Alembic** to manage versioned database migrations (`alembic revision --autogenerate`).
- **Performance Indexes**:
  - `CREATE INDEX idx_equipment_status ON Equipment(status);`
  - `CREATE INDEX idx_fields_customer ON Fields(customer_id);`
  - `CREATE INDEX idx_dispatch_status ON Dispatch_Jobs(status);`
  - `CREATE INDEX idx_incident_equipment ON Incident_Notes(equipment_id);`
  - `CREATE INDEX idx_financing_customer ON Financing_Applications(customer_id);`
  - `CREATE INDEX idx_financing_status ON Financing_Applications(status);`
  - `CREATE INDEX idx_fin_tx_app ON Financial_Transactions(application_id);`

---

## 3. Architectural Diagram Reference
- TO-BE ER Diagram: [`diagrams/to-be/database-er.mmd`](../diagrams/to-be/database-er.mmd)

