# 08. Target Security & Safety Design

## 1. Authentication & Authorization (RBAC)
- **Session Tokens**: Dispatchers authenticate via JWT containing `technician_id` and `role`.
- **Role Permissions Matrix**:

| Tool / Action | Dispatcher | Technician | Manager | Customer |
| :--- | :---: | :---: | :---: | :---: |
| `search_agricultural_knowledge` | ✅ | ✅ | ✅ | ✅ |
| `dispatch_equipment` (Standard) | ✅ | ❌ | ✅ | ❌ |
| `dispatch_equipment` (Restricted Sign-off) | Requires Sign-off | ❌ | ✅ (Approve) | ❌ |
| `emergency_stop` | ✅ | ✅ | ✅ | ❌ |
| `process_payment` | ✅ | ❌ | ✅ | ✅ (Own) |
| `generate_fleet_report` | ❌ | ❌ | ✅ | ❌ |

---

## 2. Prompt Injection Defense
- **Input Sanitization**: User inputs and unstructured incident notes are validated against delimiter injection and wrapped in strict JSON schemas.
- **System Prompt Hardening**: Core system prompts placed in immutable SystemMessage blocks with instructions prohibiting tool invocation override.
