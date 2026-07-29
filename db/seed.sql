-- ==========================
-- Seed Data
-- Run after schema.sql. Covers normal rows plus the specific
-- edge cases each protocol concern's test relies on.
-- ==========================

-- ==========================
-- Customers
-- One with credit_hold = 1 -> drives the Notifications test
-- (dispatch_equipment must be absent from tools/list for this
-- customer's sessions until the hold clears).
-- ==========================
INSERT INTO Customers (customer_id, company_name, phone, email, credit_hold) VALUES
(1, 'Nile Delta Farms',        '+20-100-111-2222', 'ops@niledeltafarms.com',   0),
(2, 'Behera Agro Cooperative', '+20-100-222-3333', 'contact@beheraagro.com',  1),  -- credit_hold = 1
(3, 'Fayoum Green Estates',    '+20-100-333-4444', 'info@fayoumgreen.com',    0);

-- ==========================
-- Fields
-- Each customer has at least one field. Field 5 (customer 3)
-- is used by the cross-customer authorization test.
-- ==========================
INSERT INTO Fields (field_id, customer_id, field_name, location, area) VALUES
(1, 1, 'North Plot A',   'Kafr El Sheikh, Block 4', 12.5),
(2, 1, 'North Plot B',   'Kafr El Sheikh, Block 5', 8.0),
(3, 2, 'Behera East',    'Damanhour, Sector 2',     20.0),
(4, 2, 'Behera West',    'Damanhour, Sector 3',     15.75),
(5, 3, 'Fayoum Oasis 1', 'Fayoum, Lakeside Road',   30.0);

-- ==========================
-- Equipment
-- Centralized fleet, statuses cover all CHECK values.
-- ==========================
INSERT INTO Equipment (equipment_id, serial_number, equipment_type, status, current_location) VALUES
(1, 'TRC-2001', 'tractor',   'idle',       'Depot A'),
(2, 'TRC-2002', 'tractor',   'dispatched', 'Kafr El Sheikh, Block 4'),
(3, 'SPR-3001', 'sprayer',   'idle',       'Depot A'),
(4, 'SPR-3002', 'sprayer',   'maintenance','Depot B'),
(5, 'HRV-4001', 'harvester', 'idle',       'Depot B'),
(6, 'HRV-4002', 'harvester', 'offline',    'Depot A');

-- ==========================
-- Technicians
-- Mix of roles and authentication states -> drives the
-- Notifications test for role-based tool visibility
-- (emergency_stop / cancel_dispatch appearing on authentication).
-- ==========================
INSERT INTO Technicians (technician_id, full_name, role, authenticated) VALUES
(1, 'Mona Adel',      'dispatcher', 1),
(2, 'Youssef Kamal',  'technician', 0),  -- not yet authenticated
(3, 'Hassan Fathy',   'technician', 1),  -- authenticated -> unlocks emergency_stop/cancel_dispatch
(4, 'Rania El-Sayed', 'manager',    1);

-- ==========================
-- Chemicals
-- Mix of hazard classes; requires_signoff drives the
-- Elicitation trigger directly from data.
-- ==========================
INSERT INTO Chemicals (chemical_id, name, hazard_class, requires_signoff) VALUES
(1, 'Glyphosate',       'restricted', 1),  -- must pause for sign-off
(2, 'Chlorpyrifos',     'controlled', 1),  -- must pause for sign-off
(3, 'Neem Oil Extract', 'low',        0),  -- completes immediately
(4, 'Foliar Fertilizer','low',        0);  -- completes immediately

-- ==========================
-- Dispatch Jobs
-- Covers: non-spray (no elicitation), spray+restricted
-- (elicitation fires), spray+low hazard (no elicitation),
-- a pending approval, and a completed job.
-- ==========================
INSERT INTO Dispatch_Jobs
    (dispatch_id, equipment_id, field_id, technician_id, job_type, chemical_id,
     status, approval_status, approved_by, requested_at, started_at, completed_at) VALUES
-- Till job, no chemical involved -> negative case for elicitation
(1, 1, 1, 1, 'till', NULL, 'completed', 'not_required', NULL,
 '2026-06-01 08:00:00', '2026-06-01 08:15:00', '2026-06-01 11:00:00'),

-- Spray job with a restricted chemical -> positive elicitation case
(2, 3, 2, 1, 'spray', 1, 'pending', 'pending', NULL,
 '2026-06-15 09:00:00', NULL, NULL),

-- Spray job with a low-hazard product -> negative elicitation case
(3, 3, 4, 1, 'spray', 3, 'dispatched', 'not_required', NULL,
 '2026-06-16 07:30:00', '2026-06-16 07:40:00', NULL),

-- Harvest job on customer 2's field, dispatched by dispatcher 1,
-- approved by an authenticated technician
(4, 5, 3, 1, 'harvest', NULL, 'approved', 'approved', 3,
 '2026-06-10 06:00:00', NULL, NULL),

-- Cancelled job -> exercises cancel_dispatch tool history
(5, 2, 1, 1, 'till', NULL, 'cancelled', 'not_required', NULL,
 '2026-06-05 08:00:00', NULL, NULL);

-- ==========================
-- Incident Notes
-- Covers every severity level and both resolved states;
-- raw_note text feeds the sampling/summarize_incident_note test.
-- ==========================
INSERT INTO Incident_Notes
    (incident_id, equipment_id, technician_id, raw_note, summarized_note, severity, resolved, created_at) VALUES
(1, 2, 3, 'machine 12 stopped near the fence line, weird noise, checked ok, restarted fine',
 NULL, 'low', 1, '2026-06-01 12:30:00'),
(2, 4, 3, 'sprayer nozzle clogged mid-job, chemical residue leaking from side panel, stopped unit immediately',
 NULL, 'high', 0, '2026-06-16 08:05:00'),
(3, 6, 2, 'harvester will not power on, no display, battery indicator dark',
 NULL, 'medium', 0, '2026-05-20 15:00:00'),
(4, 3, 3, 'sprayer tank pressure alarm triggered during restricted-chemical job, operator evacuated area, tank valve failure suspected',
 NULL, 'critical', 0, '2026-06-15 09:20:00');

-- ==========================
-- Fleet Reports
-- Covers running (in progress -> progress tracking test),
-- completed, and failed states.
-- ==========================
INSERT INTO Fleet_Reports (report_id, month, status, progress, generated_by, created_at) VALUES
(1, '2026-05', 'completed', 100, 4, '2026-06-01 00:05:00'),
(2, '2026-06', 'running',   40,  4, '2026-07-01 00:05:00'),
(3, '2026-04', 'failed',    15,  1, '2026-05-01 00:05:00');