# Decision: Adopt the Evidentia application and deployment baseline

**ID**: M71RADRBCJCY0VBD3KEG9FA020
**Status**: accepted
**Category**: technology
**Date**: 2026-10-01T16:40:39.190Z
**Author**: AI Agent + Human
**Governed Standards**: REQ-002, REQ-004, REQ-012, REQ-014, NFR-003, NFR-004, NFR-008, CON-004

## Context

Evidentia needs a self-hostable document-processing platform with a typed web interface, durable relational state, stable public contracts, replaceable storage, and deployment portability. Parser, inference, and job-runner products require evidence from representative documents and recovery tests before selection.

**Project Type**: Web Application

**Profile**: web-app

**Relevant Tech Stack**:
- Language: Python 
- Backend Framework: FastAPI 
- Language: TypeScript 
- Frontend Framework: React 
- Frontend Build Tool: Vite 
- Database: PostgreSQL 
- API: REST with OpenAPI 
- Deployment: Docker Compose 
- Identity: OIDC 



## Decision

Use Python with FastAPI for the backend; React with TypeScript and Vite for the frontend; PostgreSQL for durable relational state; versioned REST APIs with OpenAPI; local-filesystem and S3-compatible document-storage adapters; Docker Compose as the first supported deployment; and local authentication with optional OIDC. Keep parsing/OCR, extraction inference, and durable background execution behind stable interfaces. Select their default implementations only after documented quality, licensing, resource, and recovery evaluations.

This decision was made based on:

- Project requirements and constraints
- Team expertise and preferences
- Industry best practices
- Long-term maintainability



## Architecture Diagram

```mermaid
flowchart TB
    subgraph ClientLayer["🖥️ Presentation Layer"]
        App["Web / API Client"]
    end

    subgraph ServiceLayer["⚙️ Application Services"]
        Service["Business Logic / Controllers"]
        ORM["💾 Data Layer"]
    end

    subgraph StorageLayer["🗄️ Persistence"]
        DB[("💽 PostgreSQL")]
    end

    App -->|"Requests"| Service
    Service -->|"Queries & Mutations"| ORM
    ORM -->|"Driver Connection"| DB

    classDef service fill:#ebf8ff,stroke:#3182ce,stroke-width:2px,color:#2b6cb0;
    classDef storage fill:#f0fff4,stroke:#38a169,stroke-width:2px,color:#22543d;
    class Service,ORM service;
    class DB storage;
```

## Architecture Mutation (Before vs After)

```mermaid
flowchart LR
    %% Architectural Mutation Visual Diff: Before vs After

    subgraph SubgraphBefore["⏮️ Legacy Data Layer"]
        direction TB
        b_comp_app["Application Core"]
        b_comp_legacy_data["Direct SQL / Legacy Driver"]
        b_comp_app --> b_comp_legacy_data
        b_comp_legacy_db["Legacy / File DB (SQLite)"]
        b_comp_legacy_data --> b_comp_legacy_db
    end

    subgraph SubgraphAfter["⏭️ Modernized Persistence Architecture"]
        direction TB
        a_comp_app["Application Core"]
        a_comp_new_orm["Data Access Layer"]
        a_comp_app --> a_comp_new_orm
        a_comp_new_db["PostgreSQL Cluster"]
        a_comp_new_orm --> a_comp_new_db
    end

    b_comp_app -.->|"Evolution / Refactor"| a_comp_app

    %% Visual Diff Color Palettes
    classDef diffRemoved fill:#4c0519,stroke:#f43f5e,stroke-width:2px,color:#ffe4e6,stroke-dasharray: 4 4;
    classDef diffAdded fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5;
    classDef diffModified fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;
    classDef diffUnchanged fill:#1e293b,stroke:#475569,stroke-width:1px,color:#f1f5f9;
    class b_comp_app diffUnchanged;
    class b_comp_legacy_data diffRemoved;
    class b_comp_legacy_db diffRemoved;
    class a_comp_app diffModified;
    class a_comp_new_orm diffAdded;
    class a_comp_new_db diffAdded;
```

## Governing Standards

- **REQ-002**
- **REQ-004**
- **REQ-012**
- **REQ-014**
- **NFR-003**
- **NFR-004**
- **NFR-008**
- **CON-004**

## Consequences

### Positive
- Standardizes technology stack across team
- Enables consistent tooling and practices

### Negative
- Team learning curve for new technology
- Migration cost if switching later

### Neutral / Risks
- Vendor/tool lock-in risk
- Community support and hiring pool considerations

## Alternatives Considered

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |
| PostgreSQL | Robust, ACID-compliant, great JSON support | Mature; JSONB; Extensions | Operational overhead |
| MySQL | Wide adoption, good performance | Familiar; Good tooling | Weaker JSON |
| SQLite | Embedded, zero-config | Simple; Portable | No concurrency; No network |
| MongoDB | Document database, flexible schema | Flexible; Scales horizontally | No ACID (historically); Memory |
| NextAuth.js | Full-featured auth for Next.js | Built-in providers; Type-safe; Secure defaults | Next.js only; Learning curve |

## Related Requirements

No directly related requirements documented.

## Related Decisions

No related decisions documented.

## Implementation Notes

### Suggested Implementation Steps

1. Add dependency to package.json
2. Configure in application
3. Update CI/CD pipeline if needed
4. Document in team onboarding
5. Add to architecture decision log


## Validation Criteria

- [ ] Decision reviewed by team
- [ ] Alternatives documented and evaluated
- [ ] Consequences understood and accepted
- [ ] Related requirements linked
- [ ] Implementation plan created
- [ ] Dependency added to package.json
- [ ] TypeScript types available (if applicable)
- [ ] CI/CD updated if needed
- [ ] Security audit passed (if new dependency)


---

*Generated by Skyhook Auto-ADR on 2026-10-01T16:40:39.190Z*
*Review and update before marking as "accepted"*
