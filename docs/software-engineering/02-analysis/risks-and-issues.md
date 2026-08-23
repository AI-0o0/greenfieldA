# 07. Technical Debt, Risks & Architectural Issues

## 1. Critical Technical Debt
1. **Ungrounded Environment Disconnect**:
   - `GreenfieldEnvironment` claims to validate candidate plans against `farm.db`, but source inspection reveals it relies on hardcoded string keywords (e.g. checking if `"canal"` or `"15"` appears in output text).
   - *Risk*: A candidate plan could hallucinate valid phrasing while selecting an unavailable machine or invalid field.
2. **Non-Persisted Incident Reporting**:
   - `mcp_server/tools.py -> log_incident_note` does not execute an `INSERT` statement into `Incident_Notes`.
   - *Risk*: Operational safety incidents and machine faults are permanently lost upon process termination.
3. **Copy-Paste Elicitation Artifact**:
   - `mcp_client/client.py -> on_elicitation` prints a box titled `"REFUND CONFIRMATION"` when approving restricted chemical dispatches.
   - *Risk*: Operator confusion during safety sign-off.

---

## 2. Security & Safety Risks
1. **Unauthenticated MCP Tool Invocation**:
   - The FastMCP server accepts tool invocations without validating technician identity or session tokens.
   - *Impact*: Any client that connects over HTTP port 8080 can dispatch machinery or clear credit holds.
2. **Prompt Injection Risk in Unstructured Notes**:
   - User inputs passed to `log_incident_note` or agent context are not sanitized against prompt injection instructions.
3. **Single LLM Provider Lock-in**:
   - The entire reasoning loop depends on the Groq API (`openai/gpt-oss-120b`). API rate limiting or quota exhaustion halts all dispatch operations.

---

## 3. Reliability & Data Consistency Risks
1. **SQLite Concurrency Bottleneck**:
   - SQLite file-level locking blocks concurrent writes if multiple dispatch sessions execute simultaneously.
2. **Memory Loss on Crash**:
   - In-memory `ShortTermMemory` turns are held in RAM. An unhandled exception loses the conversation context before eviction to long-term memory.
