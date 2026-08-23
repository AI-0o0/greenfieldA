# Greenfield Agricultural Dispatch — Software Engineering Documentation Package

Welcome to the comprehensive Software Engineering, Reverse Engineering, and Target Architecture documentation suite for the **Greenfield Agricultural Dispatch & Fleet Logistics Planning Agent**.

---

## 📚 Documentation Directory Structure

```
docs/software-engineering/
├── README.md                                  <- Master Documentation Entry Point (You are here)
├── FINAL-REPORT.md                            <- Executive Summary & Final Architecture Report
│
├── 01-reverse-engineering/                    <- Phase 1: AS-IS Implementation Reverse Engineering
│   ├── repository-overview.md                 <- Technology stack, layout discrepancy, dependencies
│   ├── system-overview.md                     <- System purpose, actors, communications, components
│   ├── component-inventory.md                 <- Detailed source file & class catalog
│   ├── execution-flow.md                      <- Startup, REPL loop, ReAct step & slash commands
│   ├── data-architecture.md                   <- SQLite 7-table schema, seed data, CRUD mappings
│   ├── agent-architecture.md                  <- 7 planning algorithms, memory & consolidation
│   ├── mcp-architecture.md                    <- FastMCP server, 5 tools, 2 resources, 1 prompt
│   ├── rag-architecture.md                    <- ChromaDB, BM25 hybrid search, Self-RAG verifier
│   ├── workflows.md                           <- Primary AS-IS operational workflows
│   └── unknowns.md                            <- Codebase ambiguities & missing artifacts
│
├── 02-analysis/                               <- Phase 2: System & Requirements Analysis
│   ├── requirements.md                        <- Confirmed, inferred, and unknown requirements
│   ├── actors-and-use-cases.md                <- System actors & formal use cases (UC-01 to UC-11)
│   ├── functional-requirements.md             <- 15 formal FR specifications with code evidence
│   ├── non-functional-requirements.md         <- Performance, reliability, safety, maintainability
│   ├── business-rules.md                      <- Chemical buffers, wind limits, machinery rules
│   ├── gap-analysis.md                        <- AS-IS vs TO-BE gap comparison matrix
│   ├── risks-and-issues.md                    <- Technical debt, security risks, AI hazards
│   └── constraints.md                         <- Technical, regulatory, and scope boundaries
│
├── 03-design/                                 <- Phase 3: TO-BE Target Architecture & System Design
│   ├── system-design.md                       <- Target system principles & core design decisions
│   ├── architecture.md                        <- Layered enterprise architecture & protocols
│   ├── component-design.md                    <- Target component specifications & interfaces
│   ├── database-design.md                     <- Enhanced schema, audit logging & migrations
│   ├── agent-design.md                        <- LangGraph StateGraph & grounded SQL validator
│   ├── mcp-design.md                          <- FastMCP tool cleanup & atomic transactions
│   ├── rag-design.md                          <- Multi-stage RAG with RRF & Cross-Encoder rerank
│   ├── security-design.md                     <- RBAC permissions matrix & prompt injection defense
│   ├── error-handling.md                      <- Structured error taxonomy & recovery strategies
│   └── deployment-design.md                   <- Docker Compose & Kubernetes container topology
│
└── diagrams/                                  <- Complete Architecture Diagram Suite (.mmd files)
    ├── README.md                              <- Diagram catalog & status matrix
    ├── as-is/                                 <- 15 AS-IS Mermaid Architecture Diagrams
    │   ├── context.mmd                        <- C4 System Context (AS-IS)
    │   ├── container.mmd                      <- C4 Container Diagram (AS-IS)
    │   ├── component-agent.mmd                <- C4 Component Diagram for Agent (AS-IS)
    │   ├── main-execution-flow.mmd            <- Startup & REPL sequence
    │   ├── agent-execution-flow.mmd          <- Step loop sequence
    │   ├── database-er.mmd                    <- SQLite 7-table ER diagram
    │   ├── agent-architecture.mmd             <- Agent structural flowchart
    │   ├── agent-sequence.mmd                 <- Tool execution sequence
    │   ├── mcp-architecture.mmd               <- FastMCP server & client topology
    │   ├── tool-interaction.mmd               <- Tool call with elicitation sequence
    │   ├── rag-pipeline.mmd                   <- Hybrid vector + BM25 pipeline
    │   ├── use-case.mmd                       <- Use case diagram
    │   ├── workflow-01.mmd                    <- Equipment dispatch workflow
    │   ├── workflow-02.mmd                    <- Reshuffle board workflow
    │   └── workflow-03.mmd                    <- RAG knowledge search workflow
    └── to-be/                                 <- 10 TO-BE Mermaid Target Architecture Diagrams
        ├── context.mmd                        <- C4 System Context (TO-BE)
        ├── container.mmd                      <- C4 Container Diagram (TO-BE)
        ├── component-agent.mmd                <- Target LangGraph agent component diagram
        ├── component-mcp.mmd                  <- Target FastMCP server component diagram
        ├── database-er.mmd                    <- Enhanced target ER diagram with audit logs
        ├── rag-pipeline.mmd                   <- Target multi-stage RAG pipeline
        ├── deployment.mmd                     <- Container deployment topology
        ├── workflow-01.mmd                    <- Target equipment dispatch workflow
        ├── workflow-02.mmd                    <- Target reshuffle board workflow
        └── workflow-03.mmd                    <- Target RAG search workflow
```

---

## 🔍 Key Architectural Findings & Summary
1. **AS-IS System**: Python 3.14 autonomous agent running ReAct loops, FastMCP stdio client/server, ChromaDB + BM25 hybrid RAG, SQLite relational store (`farm.db`), and 7 planning algorithms.
2. **Key AS-IS Discrepancies**:
   - `GreenfieldEnvironment` uses string regex instead of live SQL queries.
   - `log_incident_note` does not persist records to SQLite.
   - `mcp_client/client.py` has a `"REFUND CONFIRMATION"` UI artifact during chemical sign-off.
   - `README.md` documents an outdated directory structure (`algorithms/` instead of `agent/algorithms/`).
3. **Target (TO-BE) Design**: Migrates agent to a LangGraph `StateGraph`, introduces live grounded SQL validation, fixes incident note persistence, enforces RBAC authentication, and containerizes the stack via Docker Compose.
