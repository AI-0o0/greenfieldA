-- ==========================
-- 1. Crop_Cases Table
-- ==========================
CREATE TABLE IF NOT EXISTS Crop_Cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    field_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'case_created',
    crop_data TEXT,
    diagnosis TEXT,
    proposed_treatment TEXT,
    dispatch_id INTEGER,
    farmer_confirmed BOOLEAN,
    observation_result TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE,
    FOREIGN KEY (field_id) REFERENCES Fields(field_id) ON DELETE CASCADE,
    FOREIGN KEY (dispatch_id) REFERENCES Dispatch_Jobs(dispatch_id) ON DELETE SET NULL
);

-- ==========================
-- 2. Crop_HITL_Tasks Table (NEW)
-- ==========================
CREATE TABLE IF NOT EXISTS Crop_HITL_Tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    case_id INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    state_snapshot TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'more_info')),
    admin_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    FOREIGN KEY (case_id) REFERENCES Crop_Cases(case_id) ON DELETE CASCADE
);