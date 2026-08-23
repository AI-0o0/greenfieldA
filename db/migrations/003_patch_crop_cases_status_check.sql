PRAGMA foreign_keys = OFF;

ALTER TABLE Crop_Cases RENAME TO Crop_Cases_old;

CREATE TABLE Crop_Cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL UNIQUE,

    customer_id INTEGER NOT NULL,
    field_id INTEGER NOT NULL,

    status TEXT NOT NULL DEFAULT 'case_created'
        CHECK (
            status IN (
                'case_created',
                'collect_crop_data',
                'diagnose',
                'propose_treatment',
                'awaiting_hitl',
                'hitl_check',
                'awaiting_farmer_confirmation',
                'farmer_confirmed',
                'declined',
                'execute_treatment',
                'treatment_started',
                'awaiting_observation',
                'evaluate_result',
                'invalid_observation',
                'recovered',
                'improved',
                'worsened',
                're_diagnose',
                'closed',
                'failed'
            )
        ),

    crop_data TEXT,
    diagnosis TEXT,
    proposed_treatment TEXT,

    dispatch_id INTEGER,

    farmer_confirmed BOOLEAN,
    observation_result TEXT,

    retry_count INTEGER NOT NULL DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)
        REFERENCES Customers(customer_id)
        ON DELETE CASCADE,

    FOREIGN KEY (field_id)
        REFERENCES Fields(field_id)
        ON DELETE CASCADE,

    FOREIGN KEY (dispatch_id)
        REFERENCES Dispatch_Jobs(dispatch_id)
        ON DELETE SET NULL
);

INSERT INTO Crop_Cases
SELECT * FROM Crop_Cases_old;

DROP TABLE Crop_Cases_old;

PRAGMA foreign_keys = ON;