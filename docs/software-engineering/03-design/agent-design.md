# 05. Target Agent & Algorithm Design

## 1. LangGraph StateGraph Architecture
The target agent replaces the sequential while-loop with an explicit state machine:

```
[Start] ──> [Classify Request] ──> [Select Algorithm / Tool]
                                           │
       ┌───────────────────────────────────┴───────────────────────────────────┐
       ▼                                   ▼                                   ▼
 [Static DAG Plan]                [Dynamic Adaptive]                  [Grounded LATS / ToT]
       │                                   │                                   │
       └───────────────────────────────────┬───────────────────────────────────┘
                                           ▼
                              [Grounded DB Validator]
                                           │
                     ┌─────────────────────┴─────────────────────┐
                     ▼                                           ▼
             (Safety Conflict)                            (Checks Passed)
                     │                                           │
         [Human Sign-off Elicit]                                 ▼
                     │                                   [Execute Tool Call]
                     ▼                                           │
           (Approved / Declined)                                 ▼
                     │                                    [Self-RAG Check]
                     └─────────────────────┬─────────────────────┘
                                           ▼
                                 [Synthesize & Output]
```

---

## 2. Grounded Validator Architecture
Replaces text heuristics with direct parameterized database queries:

```python
class GroundedSQLValidator:
    def __init__(self, db_conn):
        self.conn = db_conn

    def validate_dispatch(self, equipment_id: int, field_id: int, chemical_id: Optional[int]) -> ValidationReport:
        # 1. Live Equipment Status Query
        eq = self.conn.execute("SELECT status FROM Equipment WHERE equipment_id = ?", (equipment_id,)).fetchone()
        if not eq or eq["status"] != "idle":
            return ValidationReport(valid=False, reason=f"Equipment {equipment_id} is not idle (status={eq['status'] if eq else 'not found'})")

        # 2. Live Proximity & Buffer Query
        if chemical_id:
            chem = self.conn.execute("SELECT * FROM Chemicals WHERE chemical_id = ?", (chemical_id,)).fetchone()
            field = self.conn.execute("SELECT * FROM Fields WHERE field_id = ?", (field_id,)).fetchone()
        return ValidationReport(valid=True)
```

---

## 3. Autonomous Finance Workflow Agent (StateGraph)
Implements an interactive multi-turn state machine for agricultural finance advisory and loan applications (`agent/workflows/finance_agent.py`):
- **Advisory Pathway**: Specialist consultation (`equipment`, `crop`, `general`), single-pass Tree-of-Thoughts (`tot_advice`), Hybrid Search + Self-RAG policy grounding.
- **Financing Pathway**: Real-time eligibility checking against credit holds, document collection, financial analysis (DSCR / safe borrowing capacity ceiling), HITL admin review (`admin_review`), external provider response evaluation, farmer term confirmation (`farmer_confirm`), and cryptographic SHA-256 disbursement audit logging.
- **Diagram Reference**: [`diagrams/to-be/workflow-04-finance.mmd`](../diagrams/to-be/workflow-04-finance.mmd)

---

## 4. Persistent Fertilizer Recommendation & Follow-up State Machine
Implements a durable, asynchronous state machine spanning baseline soil telemetry, safety threshold checks, and closed-loop follow-up evaluations:
- **Baseline Soil Diagnosis**: Ingests N-P-K, pH, electrical conductivity, and organic matter metrics to generate tailored fertilizer prescriptions.
- **Safety Policy Enforcement**: Prescriptions exceeding environmental safety or canal buffer constraints automatically halt at an `admin_review` HITL checkpoint.
- **Asynchronous Checkpointing**: Enters a durable `wait_followup` state awaiting post-treatment soil telemetry.
- **Adaptive Deficiency Revision Loop**: Compares follow-up measurements against target levels. If nutrients remain deficient, routes the case back into a revised prescription loop rather than starting a new case.
- **Diagram Reference**: [`diagrams/to-be/workflow-05-fertilizer-followup.mmd`](../diagrams/to-be/workflow-05-fertilizer-followup.mmd)

