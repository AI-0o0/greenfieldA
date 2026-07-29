PRAGMA foreign_keys = ON;

-- ==========================
-- Customers
-- ==========================
CREATE TABLE Customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    phone TEXT,
    email TEXT UNIQUE,
    credit_hold BOOLEAN NOT NULL DEFAULT 0
);

-- ==========================
-- Fields
-- ==========================
CREATE TABLE Fields (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    location TEXT NOT NULL,
    area REAL NOT NULL,

    FOREIGN KEY (customer_id)
        REFERENCES Customers(customer_id)
        ON DELETE CASCADE
);

-- ==========================
-- Equipment
-- Centralized fleet: not owned by a customer directly.
-- Ownership/customer link happens per dispatch via Fields.
-- ==========================
CREATE TABLE Equipment (
    equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number TEXT NOT NULL UNIQUE,
    equipment_type TEXT NOT NULL
        CHECK (equipment_type IN ('tractor', 'sprayer', 'harvester')),
    status TEXT NOT NULL
        CHECK (status IN ('idle', 'dispatched', 'maintenance', 'offline')),
    current_location TEXT
);

-- ==========================
-- Technicians
-- ==========================
CREATE TABLE Technicians (
    technician_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (role IN ('dispatcher', 'technician', 'manager')),
    authenticated BOOLEAN NOT NULL DEFAULT 0
);

-- ==========================
-- Chemicals (lookup table)
-- Drives the elicitation trigger: a dispatch tied to a chemical
-- where requires_signoff = 1 must pause for human sign-off.
-- This keeps the "is this controlled?" decision in data, not
-- hardcoded string matching in the handler.
-- ==========================
CREATE TABLE Chemicals (
    chemical_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    hazard_class TEXT NOT NULL
        CHECK (hazard_class IN ('low', 'controlled', 'restricted')),
    requires_signoff BOOLEAN NOT NULL DEFAULT 0
);

-- ==========================
-- Dispatch Jobs
-- ==========================
CREATE TABLE Dispatch_Jobs (
    dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,

    equipment_id INTEGER NOT NULL,
    field_id INTEGER NOT NULL,
    technician_id INTEGER NOT NULL,

    job_type TEXT NOT NULL
        CHECK (job_type IN ('till', 'harvest', 'spray')),

    -- Only required when job_type = 'spray'; enforced at the
    -- handler level (server-side validation), not just by the schema.
    chemical_id INTEGER,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'approved',
                'dispatched',
                'completed',
                'cancelled',
                'stopped'
            )
        ),

    approval_status TEXT NOT NULL DEFAULT 'not_required'
        CHECK (
            approval_status IN (
                'not_required',
                'pending',
                'approved',
                'rejected'
            )
        ),

    approved_by INTEGER,

    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,

    FOREIGN KEY (equipment_id)
        REFERENCES Equipment(equipment_id),

    FOREIGN KEY (field_id)
        REFERENCES Fields(field_id),

    FOREIGN KEY (technician_id)
        REFERENCES Technicians(technician_id),

    FOREIGN KEY (chemical_id)
        REFERENCES Chemicals(chemical_id),

    FOREIGN KEY (approved_by)
        REFERENCES Technicians(technician_id)
);

-- ==========================
-- Incident Notes
-- ==========================
CREATE TABLE Incident_Notes (
    incident_id INTEGER PRIMARY KEY AUTOINCREMENT,

    equipment_id INTEGER NOT NULL,
    technician_id INTEGER NOT NULL,

    raw_note TEXT NOT NULL,
    summarized_note TEXT,

    severity TEXT
        CHECK (
            severity IN (
                'low',
                'medium',
                'high',
                'critical'
            )
        ),

    resolved BOOLEAN DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (equipment_id)
        REFERENCES Equipment(equipment_id),

    FOREIGN KEY (technician_id)
        REFERENCES Technicians(technician_id)
);

-- ==========================
-- Fleet Reports
-- ==========================
CREATE TABLE Fleet_Reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,

    month TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'running'
        CHECK (
            status IN (
                'running',
                'completed',
                'failed'
            )
        ),

    progress INTEGER DEFAULT 0
        CHECK (
            progress >= 0
            AND progress <= 100
        ),

    generated_by INTEGER,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (generated_by)
        REFERENCES Technicians(technician_id)
);