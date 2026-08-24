# Greenfield Agricultural Agency — Autonomous Multi-Agent Platform
## Final Project: Persistent Recoverable State, Dynamic Multi-Agent Orchestration & Full-Stack Platform

---

## 1. Executive Summary & Operational Rationale

High-throughput agricultural operations at **Greenfield Agricultural Agency** require coordinated decisions across biology, machinery, finance, and logistics:
- **Crop Health & Pathology:** Diagnosing crop blights, selecting compliant treatments against chemical hazard registries, and monitoring recovery over multiple growth cycles.
- **Fleet Mechanics & Maintenance:** Diagnosing machinery breakdowns, sourcing parts, scheduling field technicians, and verifying repairs before dispatch.
- **Agricultural Finance & Lending:** Underwriting multi-thousand dollar operating loans, validating farm tax returns, checking debt-service ratios, and managing capital exposure.
- **Fleet Logistics Planning:** Reshuffling daily field dispatches across hundreds of acres under weather, wind drift, and canal buffer constraints.

### Why Simple Scripts & Monolithic Agents Fail
1. **Real-World Work Spans Days & Weeks:** Workflows cannot execute start-to-finish in one pass. They must pause and wait on external physical events (lab results, parts deliveries, technician on-site visits, loan provider responses).
2. **Strict Regulatory & Financial Safety Gates:** Irreversible actions (spraying restricted neurotoxic chemicals, authorizing repairs exceeding $500, disbursing loans $\ge \$50\text{k}$) must pause for **Human-in-the-Loop (HITL)** manager approval.
3. **Mid-Node Failure Is Costly:** An unexpected API timeout, network drop, or process crash must not restart the entire multi-day case from scratch. State must be **persisted at every transition** and recoverable from the exact point of failure.
4. **Domain Complexity Requires Specialization:** A single prompt cannot act as agronomist, mechanic, underwriter, and front-desk agent without hallucinating and mixing tools. Specialized agents must operate with **least-privilege bounded contexts** and hand off tasks dynamically.

---

## 2. High-Level System Architecture

```
                                  ┌────────────────────────────────────────────────────────┐
                                  │      Greenfield Agricultural Agency Web Platform       │
                                  │         FastAPI (:8000) + Vanilla Static SPA (/)       │
                                  └──────────────────────────┬─────────────────────────────┘
                                                             │
            ┌────────────────────────────────────────────────┼────────────────────────────────────────────────┐
            ▼                                                ▼                                                ▼
┌───────────────────────────────┐        ┌────────────────────────────────┐        ┌───────────────────────────────────┐
│ User Console (Chat SPA)       │        │ Admin Console (Management SPA) │        │ Live Greenfield MCP Server        │
│ • 6-Agent Switcher            │        │ • Live Tool Matrix (Toggle)    │        │ Mounted at /mcp                   │
│ • Master Orchestrator Mode    │        │ • Dynamic RAG Document Manager │        │ Atomic Tools & Tool Registry      │
│ • Durable SQLite Threads      │        │ • Unified HITL Approvals Queue │        │ Streamable HTTP ASGI App          │
│ • Paused / Ticket Banners     │        │ • Failure & Recovery Tickets   │        │ FastMCP Provider Sync             │
└───────────────────────────────┘        └────────────────────────────────┘        └───────────────────────────────────┘
                                                             │
                                                             ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │              Unified Runtime & Seams Engine            │
                                  │   (Shared Client, Gated Clients, SQLite Checkpointers) │
                                  └──────────────────────────┬─────────────────────────────┘
                                                             │
            ┌────────────────────────────────────────────────┼────────────────────────────────────────────────┐
            ▼                                                ▼                                                ▼
┌───────────────────────────────┐        ┌────────────────────────────────┐        ┌───────────────────────────────────┐
│ 1. Crop Disease Clinic        │        │ 2. Equipment Maintenance       │        │ 3. Finance & Lending Advisor      │
│ (agents/graphs/crop_disease)  │        │ (agents/graphs/maintenance)    │        │ (agents/graphs/finance)           │
│ • RAG (+ Self-RAG)            │        │ • Task Decomposition           │        │ • Tree of Thoughts                │
│ • Whitelist Constrained ReAct │        │ • Manuals & SOPs RAG           │        │ • Underwriting Policy RAG         │
│ • HITL: Restricted Chemicals  │        │ • HITL: Cost > $500            │        │ • HITL: Loan >= $50k / DSCR<1.25  │
│ • Ticket: Retries Exhausted   │        │ • Ticket: Parts API Error      │        │ • Ticket: Valuation API 503       │
└───────────────────────────────┘        └────────────────────────────────┘        └───────────────────────────────────┘
            │                                                │                                                │
            └────────────────────────────────────────────────┼────────────────────────────────────────────────┘
                                                             │
                                                             ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │ Master Multi-Agent Orchestrator (agents/orchestrator.py)│
                                  │ Dynamic LangGraph Command(goto=...) Handoff Network    │
                                  └──────────────────────────┬─────────────────────────────┘
                                                             │
            ┌────────────────────────────────────────────────┴────────────────────────────────────────────────┐
            ▼                                                                                                 ▼
┌───────────────────────────────────────────────┐                               ┌───────────────────────────────────────────────┐
│ 4. Knowledge & Memory Assistant (Prior Lab)   │                               │ 5. Fleet Planning & Dispatch (Prior Lab)      │
│ • Front-Desk Conversational Interface         │                               │ • Multi-field Dispatch Reshuffle Board        │
│ • ReAct over Gated MCP Tools                  │                               │ • Static & Dynamic DAG Decomposition          │
│ • Short/Long-Term Semantic & Episodic Memory  │                               │ • Plan-and-Solve, ToT, Grounded LATS, Reflexion│
└───────────────────────────────────────────────┘                               └───────────────────────────────────────────────┘
```

---

## 3. The Three Stateful State-Graph Problems

### Problem 1: Crop Disease Clinic & Multi-Visit Treatment (`agents/graphs/crop_disease`)
- **Operational Reality:** Plant diseases (rust, powdery mildew, blight) require multi-visit intervention spanning days. Chemical spraying requires safety validation, farmer consent, and multi-round field observation loops.
- **Why Stateful:**
  1. Spans days between initial spray and follow-up field observations (`awaiting_observation`).
  2. Branches conditionally based on post-treatment observations (`recovered` $\rightarrow$ close, `improved` $\rightarrow$ continue monitoring, `worsened` $\rightarrow$ re-diagnose with accumulated history).
  3. Pauses for mandatory safety sign-off before dispatching restricted chemicals.
- **Two LLM Additions:**
  1. **RAG + Self-RAG Grounding Verification:** Retrieves disease manuals from vector store; Self-RAG validates retrieved chunk relevance and filters out hallucinations.
  2. **Whitelist-Constrained ReAct:** Validates chemical options against the live `Chemicals` table and verifies idle sprayer availability in `Equipment`.
- **HITL Policy:** Chemical with `requires_signoff = 1` or hazard class `restricted` / `controlled` immediately halts execution and files a task in `Crop_HITL_Tasks`.
- **Failure Recovery:** Diagnostic retry budget exhaustion ($\ge 3$ ungrounded attempts) or sprayer dispatch error opens an inspectable ticket in `Tickets`.

### Problem 2: Agricultural Financing & Multi-Turn Lending Workflow (`agents/graphs/finance`)
- **Operational Reality:** Farm financing applications cannot complete in a single turn. They require document uploads, underwriting policy checks, credit committee reviews, external provider decisions, and farmer term acceptance.
- **Why Stateful:**
  1. Explicit multi-turn waiting states: `wait_farmer` (document submission), `wait_provider` (external lending institution response), and `farmer_confirm` (accepting loan APR & terms).
  2. Remediation cycles: Missing documents loop back from `validate_documents` to `collect_documents`.
  3. Provider rejections branch into alternative loan option generation.
- **Two LLM Additions:**
  1. **Tree of Thoughts (ToT):** Explores combinatorial credit permutations, assessing debt-service coverage ratios ($\text{DSCR}$), loan terms, and risk ratings.
  2. **Policy RAG:** Ingests internal underwriting policies (`agricultural_finance_policies.txt`) to enforce collateral rules and debt limits.
- **HITL Policy:** Applications triggering high capital exposure (amount $\ge \$50,000$), low debt margin ($\text{DSCR} < 1.25$), or elevated risk rating halt at `admin_review` and file a task in `HITL_Tasks`.
- **Failure Recovery:** Unplanned valuation API failures (503 Service Unavailable) or appraisal calculation errors open a ticket in `Tickets`.

### Problem 3: Equipment Maintenance & Repair Workflow (`agents/graphs/maintenance`)
- **Operational Reality:** Machinery breakdowns (sprayer pump leaks, tractor transmission slippage) require a multi-day lifecycle: intake, troubleshooting, task decomposition, technician on-site visits, spare parts shipments, and field load testing.
- **Why Stateful:**
  1. Spans days waiting for field technician arrival (`awaiting_technician_visit`) and supplier parts shipment (`awaiting_parts_delivery`).
  2. Operational testing loop (`awaiting_testing_confirmation`): `passed` $\rightarrow$ restores equipment status to `idle`; `failed` $\rightarrow$ loops back to re-diagnosis.
- **Two LLM Additions:**
  1. **Task Decomposition:** Decomposes complex repair into 4 ordered operational milestones: `[1. Physical Inspection & Teardown, 2. Parts Sourcing & Delivery, 3. Component Assembly & Torque Calibration, 4. Operational Load Testing]`.
  2. **Manuals & SOPs RAG:** Queries ChromaDB for equipment manuals (`equipment_manuals.txt`) to diagnose root cause and identify required part numbers.
- **HITL Policy:** Total estimated repair cost (parts + labor) exceeding **$500.00** halts execution at `hitl_cost_approval` and files a task in `HITL_Tasks`.
- **Failure Recovery:** External parts inventory API timeouts (504) or technician scheduling conflicts open a ticket in `Tickets`.

---

## 4. Dynamic Multi-Agent Orchestration & Dynamic Handoffs

### Why Multi-Agent Collaboration with Dynamic Handoffs is Essential
In production enterprise architectures, a monolithic "god-agent" fails for four fundamental reasons:
1. **Domain Specialization & Cognitive Isolation:** An agronomist diagnosing plant pathology needs disease manuals and symptom prompts; a mechanic needs hydraulic torque specs and parts catalogs; a financial underwriter needs amortization math and credit policies. Combining all tools into one agent causes prompt bloat, tool confusion, and severe hallucinations.
2. **Context & State Segregation (Least Privilege):** Each agent maintains an isolated, typed state schema (`CaseState`, `FinanceState`, `MaintenanceState`) preventing private financial data or complex mechanical logs from leaking into unrelated conversations.
3. **Dynamic vs. Brittle Static Pipelines:** Real-world farm operations branch unpredictably. A conversation starting with crop yellowing may reveal an underlying sprayer defect, which in turn uncovers high repair costs that necessitate a repair loan. A static DAG cannot handle this dynamic emergence; a **Dynamic Handoff Network** can.
4. **Auditability & Clear Departmental Ownership:** Every handoff is an explicit `Command(goto=target_agent, update={...})` transition recorded in durable SQLite storage with full timestamps and reasoning.

### The Real-World Cross-Domain Case Study

```
┌──────────────┐
│ Farmer Inquiry│ "My wheat field is failing because sprayer SPR-3001 had a hydraulic breakdown.
└──────┬───────┘  We need to fix the sprayer and arrange financing if it's expensive."
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ 1. Front-Desk Conversational Agent (agents/agent.py)   │ Welcomes farmer with memory context.
│                                                        │ Dynamic Handoff: transfer_to_crop_disease
└───────────────────────┬────────────────────────────────┘
                        │ Command(goto="crop_disease")
                        ▼
┌────────────────────────────────────────────────────────┐
│ 2. Crop Disease Clinic (agents/graphs/crop_disease)    │ Diagnoses uneven chemical application.
│                                                        │ Identifies root cause as sprayer pressure loss.
│                                                        │ Dynamic Handoff: transfer_to_maintenance
└───────────────────────┬────────────────────────────────┘
                        │ Command(goto="maintenance")
                        ▼
┌────────────────────────────────────────────────────────┐
│ 3. Equipment Maintenance (agents/graphs/maintenance)   │ RAG manual lookup & 4-stage repair plan.
│                                                        │ Estimates hydraulic pump overhaul = $1,200 (> $500 HITL).
│                                                        │ Dynamic Handoff: transfer_to_finance
└───────────────────────┬────────────────────────────────┘
                        │ Command(goto="finance")
                        ▼
┌────────────────────────────────────────────────────────┐
│ 4. Finance Advisor (agents/graphs/finance)             │ Underwrites $1,200 repair loan (12-mo @ 5.25% APR).
│                                                        │ Approves credit facility and prepares terms.
│                                                        │ Dynamic Handoff: transfer_to_frontdesk
└───────────────────────┬────────────────────────────────┘
                        │ Command(goto="frontdesk")
                        ▼
┌────────────────────────────────────────────────────────┐
│ 5. Front-Desk Synthesis (agents/agent.py)              │ Synthesizes biological diagnosis, repair schedule,
│                                                        │ and loan terms into a clear, comforting response.
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌──────────────┐
│ Farmer Clarity│ Complete multi-department resolution delivered in a single unified session!
└──────────────┘
```

---

## 5. Strict Principle of Least Privilege: Context & Tool Scoping

To prevent unauthorized operations and context contamination, tool access and context visibility are strictly enforced across two layers:
1. **API & Database Tool Gating (`Agent_Tool_Registry`):** The runtime wraps the shared MCP client in a `GatedMCPClient` that validates tool permissions on every call.
2. **State & Memory Boundary Gating:** Each state graph operates on its own scoped schema.

```
                                      AGENT TOOL PERMISSION MATRIX
┌───────────────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ MCP Tool Name         │ Front-Desk   │ Crop Disease │ Maintenance  │ Finance      │ Fleet Plan   │ Master Orch  │
├───────────────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ search_agricultural_kn│   ENABLED    │   ENABLED    │   ENABLED    │   ENABLED    │   ENABLED    │   ENABLED    │
│ log_incident_note     │   ENABLED    │   ENABLED    │   ENABLED    │   DISABLED   │   DISABLED   │   ENABLED    │
│ dispatch_equipment    │   DISABLED   │   ENABLED    │   DISABLED   │   DISABLED   │   DISABLED   │   DISABLED   │
│ get_equipment_status  │   DISABLED   │   DISABLED   │   ENABLED    │   DISABLED   │   ENABLED    │   ENABLED    │
│ process_payment       │   DISABLED   │   DISABLED   │   DISABLED   │   ENABLED    │   DISABLED   │   DISABLED   │
│ batch_dispatch        │   DISABLED   │   DISABLED   │   DISABLED   │   DISABLED   │   ENABLED    │   DISABLED   │
│ generate_fleet_report │   DISABLED   │   DISABLED   │   DISABLED   │   DISABLED   │   ENABLED    │   DISABLED   │
└───────────────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

---

## 6. Durable Persistence & Crash-Recovery Proof

All state graphs and the orchestrator are wired to durable SQLite checkpointers (`langgraph-checkpoint-sqlite`) on `db/farm.db`. 

### Crash-and-Resume Verification
When the platform process is terminated mid-run (e.g. `SIGKILL`, crash, power failure):
1. Every state transition has already been committed to `db/farm.db`.
2. Upon process restart, `graph.get_state(config)` reloads the exact node location, variables, and interrupt payload.
3. Resuming execution proceeds directly from the pending interrupt or failed checkpoint without re-running any completed nodes.

---

## 7. Web Platform & API Reference

The platform provides a single FastAPI service (`website/backend/main.py`) hosting the live FastMCP endpoint at `/mcp` and the static single-page application at `/`.

### REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Healthcheck returning MCP endpoint status and graph readiness |
| `GET` | `/api/agents` | Lists all 6 configured agents with descriptions, techniques, and wait states |
| `POST` | `/api/threads/new?agent_id={id}` | Creates a new durable conversation thread |
| `POST` | `/api/chat` | Unified chat dispatch routing turns to the active agent |
| `GET` | `/api/admin/tools` | Fetches the full Agent Tool Matrix and live server `tools/list` |
| `POST` | `/api/admin/tools/toggle` | Toggles tool enablement for an agent with immediate live FastMCP sync |
| `GET` | `/api/admin/tools/verify` | Verifies registry consistency against live server visibility |
| `GET` | `/api/admin/documents` | Lists all ingested knowledge base documents with chunk counts |
| `POST` | `/api/admin/documents` | Ingests a `.txt` document into ChromaDB with deterministic chunk IDs |
| `DELETE`| `/api/admin/documents/{name}` | Deletes all chunks for a document; immediately reflected in next retrieval |
| `GET` | `/api/hitl` | Lists all pending and resolved HITL approval tasks across all graphs |
| `GET` | `/api/hitl/{kind}/{task_id}` | Detailed inspection of a HITL task including full state snapshot |
| `POST` | `/api/hitl/{kind}/{task_id}/resolve` | Resolves a HITL task (`approve` / `reject` / `more_info`) and resumes run |
| `GET` | `/api/tickets` | Lists all open, investigating, and resolved failure tickets |
| `POST` | `/api/tickets/{id}/investigate` | Updates ticket status to `investigating` with admin notes |
| `POST` | `/api/tickets/{id}/resolve` | Resolves failure ticket with optional state patch and resumes from checkpoint |
| `GET` | `/api/threads/{agent_id}/{thread_id}` | Non-advancing state snapshot inspector for thread state debugging |

---

## 8. Extension and Correction of Prior Labs

This project directly reuses and corrects all prior course deliverables:
- **MCP Server Lab:** Corrected port drift between client and server (`:8000` vs `:8080`) by standardizing in `config.py`. Added dynamic runtime tool registration/deregistration in `mcp_server/tool_manager.py`.
- **Memory & RAG Lab:** Extended ChromaDB vector store in `rag/vector_store.py` with runtime document listing, ingestion, and deletion immediately queried by `knowledge_assistant`.
- **Decomposition & Planning Lab:** Preserved all planning algorithms (Static DAG, Dynamic DAG, Plan-and-Solve, Tree of Thoughts, Grounded LATS, Reflexion, Self-Refine) within `fleet_planner`.

---

## 9. Getting Started & Verification Guide

### 1. Environment Setup & Dependencies
```bash
# Clone repository
git clone https://github.com/your-org/greenfield-mcp-dispatch.git
cd greenfield-mcp-dispatch

# Install dependencies using uv
uv sync
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```bash
GROQ_API_KEY=your_groq_api_key_here
GREENFIELD_DB_PATH=db/farm.db
```

### 3. Launch the Web Platform
```bash
uv run uvicorn website.backend.main:app --host 127.0.0.1 --port 8000
```
Open your browser at `http://127.0.0.1:8000` to interact with both the **User Console** and **Admin Console**.

### 4. Run the Full Test Suite
```bash
# Run all unit and integration tests across state graphs and platform
uv run pytest
```
