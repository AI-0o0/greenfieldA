# 09. Target Error Handling & Resilience Design

## 1. Structured Error Taxonomy

| Error Class | Root Cause Example | Target Handling & Recovery Strategy |
| :--- | :--- | :--- |
| **`ValidationError`** | Invalid dispatch arguments or schema mismatch | Return structured JSON error to agent; agent self-corrects arguments in next turn without crashing. |
| **`BusinessRuleViolation`** | Wind > 15 km/h, canal buffer < 15m | Emit domain feedback detail to agent; trigger `Reflexion` or `LATS` branch exploration for alternative plan. |
| **`ElicitationCancelled`** | Supervisor denies chemical sign-off | Mark `approval_status = 'rejected'`, abort dispatch, notify dispatcher with supervisor notes. |
| **`DatabaseLockError`** | Concurrent SQLite write contention | Exponential backoff retry (up to 3 retries, 100ms jitter) before raising system fault. |
| **`LLMRateLimitError`** | Groq API 429 Rate Limit | Fall back to secondary LLM provider (Mistral / OpenAI) or pause execution with backoff. |
| **`RAGGroundingFailure`** | Self-RAG flags answer as unsupported | Reformulate search query automatically via agentic RAG loop; if 2 hops fail, escalate to human. |
