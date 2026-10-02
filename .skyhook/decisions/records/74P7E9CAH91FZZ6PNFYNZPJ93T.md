# Decision: Use a pluggable approval boundary with optional Delibera integration

**ID**: 74P7E9CAH91FZZ6PNFYNZPJ93T
**Status**: accepted
**Category**: architecture
**Date**: 2026-10-01T16:35:39.953Z
**Author**: AI Agent + Human
**Governed Standards**: REQ-008, REQ-009, CON-002, NFR-003, NFR-008

## Context

Evidentia needs trustworthy revision-bound authorization but must remain independently useful. Delibera will be developed in another workspace and cannot be a mandatory runtime or data dependency.

**Project Type**: Web Application

**Profile**: web-app



## Decision

Define an ApprovalAdapter owned by Evidentia. Ship a secure local/manual implementation for standalone operation and support Delibera as an optional external adapter through authenticated versioned contracts. Never query Delibera's database directly and never silently fall back after integration failure.

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
        DB[("💽 Database")]
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

    subgraph SubgraphBefore["⏮️ Legacy Session Auth"]
        direction TB
        b_comp_client["Client Browser"]
        b_comp_old_auth["Stateful Session Store / Cookies"]
        b_comp_client --> b_comp_old_auth
        b_comp_api["Backend API Service"]
        b_comp_old_auth --> b_comp_api
    end

    subgraph SubgraphAfter["⏭️ Decoupled Modern Auth Flow"]
        direction TB
        a_comp_client["Client Browser"]
        a_comp_new_auth["JWT Bearer Authentication"]
        a_comp_client --> a_comp_new_auth
        a_comp_api["Backend API (Stateless Validation)"]
        a_comp_new_auth --> a_comp_api
    end

    b_comp_client -.->|"Evolution / Refactor"| a_comp_client

    %% Visual Diff Color Palettes
    classDef diffRemoved fill:#4c0519,stroke:#f43f5e,stroke-width:2px,color:#ffe4e6,stroke-dasharray: 4 4;
    classDef diffAdded fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5;
    classDef diffModified fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;
    classDef diffUnchanged fill:#1e293b,stroke:#475569,stroke-width:1px,color:#f1f5f9;
    class b_comp_client diffUnchanged;
    class b_comp_old_auth diffRemoved;
    class b_comp_api diffUnchanged;
    class a_comp_client diffModified;
    class a_comp_new_auth diffAdded;
    class a_comp_api diffModified;
```

## Governing Standards

- **REQ-008**
- **REQ-009**
- **CON-002**
- **NFR-003**
- **NFR-008**

## Consequences

### Positive
- Improves system modularity and maintainability
- Enables independent scaling of components

### Negative
- Increased operational complexity
- Network latency between services

### Neutral / Risks
- Requires robust observability and monitoring
- Distributed tracing and debugging complexity

## Alternatives Considered

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
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

- **9M0TE8Z5N6VWW459X5N1P7EG95**: Plan the complete Evidentia platform through capability gates (accepted)

## Implementation Notes

### Suggested Implementation Steps

1. Create module/service boundaries
2. Define interfaces/contracts
3. Implement communication layer
4. Add observability (logging, metrics, tracing)
5. Update deployment configuration


## Validation Criteria

- [ ] Decision reviewed by team
- [ ] Alternatives documented and evaluated
- [ ] Consequences understood and accepted
- [ ] Related requirements linked
- [ ] Implementation plan created


---

*Generated by Skyhook Auto-ADR on 2026-10-01T16:35:39.953Z*
*Review and update before marking as "accepted"*
