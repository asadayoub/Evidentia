# Decision: Use capability-based provider ports for document understanding, extraction, and delivery

**ID**: Y87ZMJGAW6CGY7MSPDYKJ2W436
**Status**: accepted
**Category**: architecture
**Date**: 2026-10-08T07:26:22.714Z
**Author**: AI Agent + Human
**Governed Standards**: STD-ARCH-001, STD-ARCH-002, STD-ARCH-004, STD-SOFT-003

## Context

Evidentia must support native parsers, OCR services, structured extraction systems, and later destination platforms without coupling its domain model, schema lifecycle, credentials, or authoritative records to any vendor. Provider capabilities and execution models vary, including synchronous and asynchronous jobs, layout fidelity, language support, evidence coordinates, tables, and structured output.

**Project Type**: Web Application

**Profile**: web-app

**Relevant Tech Stack**:
- Language: Python 3.14.x
- Language: TypeScript 



## Decision

Define separate owned ports for native parsing, OCR, schema-directed extraction, and authorized destination delivery. Use versioned request/result envelopes, capability discovery, normalized provenance and error taxonomies, deterministic idempotency and retry/cancellation semantics, and adapter-scoped configuration and credentials. Providers may return candidates and evidence against an immutable published schema but may not mutate schema definitions or authoritative reviewed revisions. Maintain conformance tests for adapters and retain vendor-specific payloads only as protected diagnostic artifacts outside the core domain model.

This decision was made based on:

- Project requirements and constraints
- Team expertise and preferences
- Industry best practices
- Long-term maintainability



## Architecture Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as 👤 User Client
    participant App as 🖥️ Application Gateway
    participant Auth as 🔐 Auth Provider / JWT
    participant Resource as 📦 Protected API / DB

    User->>App: 1. Login Request (Credentials / OAuth)
    App->>Auth: 2. Validate & Issue Credentials
    Auth-->>App: 3. Return Signed Token / Session
    App-->>User: 4. Set Secure Cookie / Token
    User->>App: 5. Request Protected Route + Token
    App->>Auth: 6. Verify Signature & Claims
    Auth-->>App: 7. Token Validated
    App->>Resource: 8. Execute Authorized Action
    Resource-->>User: 9. Secure Response Data
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

- **STD-ARCH-001**
- **STD-ARCH-002**
- **STD-ARCH-004**
- **STD-SOFT-003**

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
| NextAuth.js | Full-featured auth for Next.js | Built-in providers; Type-safe; Secure defaults | Next.js only; Learning curve |
| Clerk | Managed auth service | Drop-in; MFA built-in; Admin dashboard | Cost; Vendor lock-in |
| Supabase Auth | Open-source auth with Postgres | Integrated with DB; Open source | Self-host complexity |
| Custom JWT | Roll your own with jsonwebtoken | Full control; No deps | Security risk; Maintenance burden |

## Related Requirements

No directly related requirements documented.

## Related Decisions

- **9M0TE8Z5N6VWW459X5N1P7EG95**: Plan the complete Evidentia platform through capability gates (accepted)
- **74P7E9CAH91FZZ6PNFYNZPJ93T**: Use a pluggable approval boundary with optional Delibera integration (accepted)
- **QQAK9DE77WFYENB2474V7XJW8W**: Adopt an accessibility-first dense review interface (accepted)
- **4SWENJ85M4CKNH60Q071BFK2WW**: Use a bounded invoice benchmark with extensible document processing (accepted)
- **GNCDV7AB7331S5JN3FXTGB6QZJ**: Use schema-driven dynamic records with reproducible context resolution (superseded)

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

*Generated by Skyhook Auto-ADR on 2026-10-08T07:26:22.714Z*
*Review and update before marking as "accepted"*
