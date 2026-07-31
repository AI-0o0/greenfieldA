# Greenfield Fleet Dispatch — MCP Server

## Company & Problem
[Role 1 territory, but everyone should read it]
- Who Greenfield is: an equipment-as-a-service company that owns a fleet of
  autonomous farm machinery (tractors, sprayers, harvesters) and dispatches
  it to customer farms on request.
- What existed before: describe the naive version — e.g. dispatchers had raw
  DB/console access, or a human manually approved every request by phone.
  Make the risk concrete: an LLM with unscoped DB access could dispatch a
  restricted-chemical sprayer with no oversight, bill the wrong customer, or
  leak which fields belong to which customer.
- Why this needed an MCP server instead of direct DB access: scoped,
  auditable, protocol-level control over what an LLM can see and do.

## Database & ERD
[Role 1]
- Engine used (SQLite, per your seed data)
- ERD (Mermaid source or image) — Customers, Fields, Equipment, Technicians,
  Chemicals, Dispatch_Jobs, Incident_Notes, Fleet_Reports
- Note on edge cases the seed data covers: a customer on credit_hold, a
  cross-customer field-ownership case, equipment in every status
  (idle/dispatched/maintenance/offline), chemicals with and without
  requires_signoff

## Protocol Concerns — how each one shows up

For each, name the file/function where a grader can find it, the trigger,
and the test case that proves it (pull straight from tests.json / your
teammate's scripts):

### Capability negotiation
[Yours to draft]
- Server declares: tools, resources, prompts (via FastMCP's automatic
  initialize handling)
- Client checks server capabilities before relying on them: [file/line in
  agent/ where init_result.capabilities is actually branched on]
- Server also checks client capabilities: dispatch_equipment refuses spray
  jobs for clients that didn't declare elicitation support
- Test: TC-XX

### Notifications
[Role 3]
- Trigger: credit_hold clearing / technician authentication
- What appears/disappears: dispatch_equipment, emergency_stop, cancel_dispatch
- Test: [the session-identity test flagged earlier — still needs building]

### Elicitation
[Yours]
- Trigger: job_type == "spray" AND chemical.requires_signoff == 1
- File: mcp_server/server.py, dispatch_equipment handler
- Outcomes handled: accept/approved, accept/denied, decline, cancel
- Test: TC04, TC05

### Sampling
[Role 3]
- What it's for: structuring free-text incident notes
- Uses the client's model, not the server's own key
- Test: TC15

### Resources
[Role 1]
- pesticide_compliance_policy exposed via resources/read, not a tool
- Test: [separate resources/prompts script — flag if not built yet]

### Prompts
[Role 1]
- draft_delay_explanation(dispatch_id) template
- Test: [same as above]

### Transport
[Role 1, but state ownership matters for grading]
- stdio for local dev, Streamable HTTP for deployment
- Point to the actual commit where this transition happened

### Progress tracking
[Role 3]
- batch_dispatch reports intermediate progress, not one blocking call
- Test: TC14

### Defensive tool design
[Yours]
- dispatch_equipment: strict schema (Literal enums, additionalProperties:
  false), independent handler-level checks (existence, ownership,
  availability), separate from schema validation
- Test: TC07–TC12

## Comparison Note
[Team — but you should draft the tool table since it's your tools]
| Tool | Read/Write | Requires elicitation? | Why |
|---|---|---|---|
| dispatch_equipment | Write | Only for spray + requires_signoff chemical | irreversible, regulated action |
| cancel_dispatch | Write | No | reversible, low-stakes |
| batch_dispatch | Write | No | long-running but not risky |
| check_equipment_status | Read | No | — |
| get_dispatch_status | Read | No | — |

What happens if a client connects without a needed capability: [describe
your fallback — dispatch_equipment refuses spray jobs cleanly rather than
hanging or silently proceeding]

## Running It
[Role 3 — setup/run instructions, env vars, how to run tests.json]

## What we'd still worry about in production
[Team, write together right before the presentation — this is presentation
material as much as README material: rate limiting, real auth instead of a
trusted customer_id field, what happens if elicitation times out for real,
etc.]
