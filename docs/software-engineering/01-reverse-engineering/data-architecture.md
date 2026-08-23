# 05. Data Architecture & Storage Reverse Engineering

## 1. Database Overview
The relational data layer is implemented in SQLite3 ([`db/farm.db`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/farm.db)) using pure DDL scripts without an ORM framework.

- **Schema Definition**: [`db/schema.sql`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql)
- **Seed Data**: [`db/seed.sql`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/seed.sql)
- **Foreign Keys**: Enabled via `PRAGMA foreign_keys = ON;` ([`db/schema.sql:1`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L1))

---

## 2. Table Specifications & Constraints

### 1. `Customers` Table ([`db/schema.sql:6-12`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L6-L12))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `customer_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique customer ID |
| `company_name`| `TEXT` | `NOT NULL` | Farm / Agricultural enterprise name |
| `phone` | `TEXT` | - | Contact phone number |
| `email` | `TEXT` | `UNIQUE` | Contact email address |
| `credit_hold` | `BOOLEAN` | `NOT NULL DEFAULT 0` | 1 = Active credit hold (blocks dispatches) |

### 2. `Fields` Table ([`db/schema.sql:17-27`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L17-L27))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `field_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique field identifier |
| `customer_id` | `INTEGER` | `NOT NULL, FK -> Customers(customer_id) ON DELETE CASCADE` | Owning customer |
| `field_name` | `TEXT` | `NOT NULL` | Descriptive name (e.g. 'North Plot A') |
| `location` | `TEXT` | `NOT NULL` | Geographic description / sector |
| `area` | `REAL` | `NOT NULL` | Field size in acres/feddans |

### 3. `Equipment` Table ([`db/schema.sql:34-42`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L34-L42))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `equipment_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique machinery ID |
| `serial_number`| `TEXT` | `NOT NULL UNIQUE` | Machine serial (e.g. 'SPR-3001') |
| `equipment_type`| `TEXT` | `CHECK (equipment_type IN ('tractor', 'sprayer', 'harvester'))` | Equipment classification |
| `status` | `TEXT` | `CHECK (status IN ('idle', 'dispatched', 'maintenance', 'offline'))` | Current operational state |
| `current_location`| `TEXT`| - | Current depot or field location |

### 4. `Technicians` Table ([`db/schema.sql:47-53`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L47-L53))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `technician_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique technician ID |
| `full_name` | `TEXT` | `NOT NULL` | Staff member name |
| `role` | `TEXT` | `CHECK (role IN ('dispatcher', 'technician', 'manager'))` | Organizational role |
| `authenticated`| `BOOLEAN` | `NOT NULL DEFAULT 0` | Security auth flag |

### 5. `Chemicals` Table ([`db/schema.sql:62-68`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L62-L68))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `chemical_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique chemical ID |
| `name` | `TEXT` | `NOT NULL UNIQUE` | Chemical name (e.g. 'Glyphosate') |
| `hazard_class` | `TEXT` | `CHECK (hazard_class IN ('low', 'controlled', 'restricted'))` | Toxicity category |
| `requires_signoff`| `BOOLEAN`| `NOT NULL DEFAULT 0` | If 1, triggers FastMCP elicitation sign-off |

### 6. `Dispatch_Jobs` Table ([`db/schema.sql:73-129`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L73-L129))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `dispatch_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Unique dispatch record ID |
| `equipment_id` | `INTEGER` | `FK -> Equipment(equipment_id)` | Assigned machine |
| `field_id` | `INTEGER` | `FK -> Fields(field_id)` | Destination field |
| `technician_id`| `INTEGER` | `FK -> Technicians(technician_id)` | Assigned operator/dispatcher |
| `job_type` | `TEXT` | `CHECK (job_type IN ('till', 'harvest', 'spray'))` | Operation type |
| `chemical_id` | `INTEGER` | `FK -> Chemicals(chemical_id)` | Applied chemical (spray jobs only) |
| `status` | `TEXT` | `CHECK (status IN ('pending', 'approved', 'dispatched', 'completed', 'cancelled', 'stopped'))` | Job lifecycle status |
| `approval_status`| `TEXT` | `CHECK (approval_status IN ('not_required', 'pending', 'approved', 'rejected'))` | Sign-off state |
| `approved_by` | `INTEGER` | `FK -> Technicians(technician_id)` | Authorizing technician |
| `requested_at` | `DATETIME`| `DEFAULT CURRENT_TIMESTAMP` | Submission timestamp |
| `started_at` | `DATETIME`| - | Commencement timestamp |
| `completed_at` | `DATETIME`| - | Completion timestamp |

### 7. `Incident_Notes` Table ([`db/schema.sql:134-163`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L134-L163))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `incident_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Incident ID |
| `equipment_id` | `INTEGER` | `FK -> Equipment(equipment_id)` | Involved equipment |
| `technician_id`| `INTEGER` | `FK -> Technicians(technician_id)` | Reporting technician |
| `raw_note` | `TEXT` | `NOT NULL` | Unstructured observation text |
| `summarized_note`| `TEXT` | - | Compacted summary |
| `severity` | `TEXT` | `CHECK (severity IN ('low', 'medium', 'high', 'critical'))` | Severity rating |
| `resolved` | `BOOLEAN` | `DEFAULT 0` | Resolution flag |
| `created_at` | `DATETIME`| `DEFAULT CURRENT_TIMESTAMP` | Creation timestamp |

### 8. `Fleet_Reports` Table ([`db/schema.sql:167-193`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L167-L193))
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `report_id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Report ID |
| `month` | `TEXT` | `NOT NULL` | Target month ('YYYY-MM') |
| `status` | `TEXT` | `CHECK (status IN ('running', 'completed', 'failed'))` | Generation status |
| `progress` | `INTEGER` | `CHECK (progress >= 0 AND progress <= 100)` | Progress percentage |
| `generated_by` | `INTEGER` | `FK -> Technicians(technician_id)` | Authorizing technician |
| `created_at` | `DATETIME`| `DEFAULT CURRENT_TIMESTAMP` | Report creation timestamp |

---

## 3. CRUD Operations Mapped to Source Code
- **`dispatch_equipment`** ([`mcp_server/tools.py:127-221`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L127-L221)):
  - `SELECT` on `Customers`, `Fields`, `Equipment`, `Chemicals`, `Technicians`.
  - `INSERT` into `Dispatch_Jobs`.
  - `UPDATE` on `Equipment` (sets `status = 'dispatched'`).
- **`batch_dispatch`** ([`mcp_server/tools.py:78-82`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L78-L82)):
  - `UPDATE` on `Equipment` for each ID in batch.
- **`process_payment`** ([`mcp_server/tools.py:65-68`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L65-L68)):
  - `INSERT OR IGNORE` into `CUSTOMERS` and `UPDATE CUSTOMERS SET credit_hold = 0`.
- **`equipment_status_snapshot`** ([`mcp_server/server.py:97-109`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L97-L109)):
  - `SELECT` on `Equipment`.
- **`draft_delay_explanation`** ([`mcp_server/server.py:131-147`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L131-L147)):
  - `SELECT` joining `Dispatch_Jobs`, `Fields`, and `Customers`.
- **`log_incident_note`** ([`mcp_server/tools.py:93-96`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L93-L96)):
  - ⚠️ **Defect**: Does not execute any SQL `INSERT` to `Incident_Notes`; returns formatted string only.

---

## 4. Non-Relational Storage
- **`long_term_memory.json`** ([`long_term_memory.json:1-27`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/long_term_memory.json#L1-L27)):
  - Stores two root keys: `semantic_facts` (versioned key-value facts with update history) and `episodic_events` (chronological list of interactions with consolidation status).
- **ChromaDB (`rag/vector_store_data/`)**:
  - Embedded vector database files storing 384-dimensional cosine embeddings generated by `all-MiniLM-L6-v2`.

---

## 5. Architectural Diagram Reference
- Entity-Relationship Diagram: [`diagrams/as-is/database-er.mmd`](../diagrams/as-is/database-er.mmd)
