# 10. Target Deployment & Infrastructure Design

## 1. Containerized Service Topology
The target system deploys via Docker Compose / Kubernetes:

```
┌─────────────────────────────────────────────────────────────┐
│ NGINX Ingress Reverse Proxy (TLS 1.3 Termination, Port 443) │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────┐┌──────────────▼───────────────┐
│ greenfield-api Container    ││ greenfield-worker Container  │
│ (FastAPI Platform Backend)  ││ (LangGraph Planning Agent)   │
└──────────────┬──────────────┘└──────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────┐┌──────────────▼───────────────┐
│ greenfield-mcp Container    ││ Redis 7 Container            │
│ (FastMCP Server stdio/SSE)  ││ (State Cache & Session Store)│
└──────────────┬──────────────┘└──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│ Persistent Data Volumes: PostgreSQL 16 & ChromaDB Store     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Docker Compose Specification (`docker-compose.yml`)

```yaml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://greenfield:secret@db:5432/farm_prod
      - REDIS_URL=redis://cache:6379/0
      - GROQ_API_KEY=${GROQ_API_KEY}
    depends_on:
      - db
      - cache

  mcp-server:
    build:
      context: .
      dockerfile: docker/Dockerfile.mcp
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://greenfield:secret@db:5432/farm_prod
    depends_on:
      - db

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=greenfield
      - POSTGRES_PASSWORD=secret
      - POSTGRES_DB=farm_prod
    volumes:
      - pgdata:/var/lib/postgresql/data

  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

---

## 3. Architectural Diagram Reference
- TO-BE Deployment Diagram: [`diagrams/to-be/deployment.mmd`](../diagrams/to-be/deployment.mmd)
