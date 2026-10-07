# Decision: Use replaceable bounded authentication throttling

**ID**: TXEQ9J0ARXYKS7CMQ0V1Z9FT5R
**Status**: accepted
**Category**: security
**Date**: 2026-10-07T10:19:33.133Z
**Author**: AI Agent + Human
**Governed Standards**: STD-ARCH-001, STD-SEC-001, STD-SEC-003, STD-SOFT-001

## Context

Local authentication needs bounded brute-force resistance now, while the current native development runtime is single-process. A permanent account lockout would enable denial of service, and introducing Redis or another shared service before multi-instance deployment would add infrastructure before it is operationally required.

**Project Type**: Web Application

**Profile**: web-app

**Relevant Tech Stack**:
- API: REST with OpenAPI 
- Deployment: Docker Compose 



## Decision

Define authentication throttling as an application port. Use a process-local exponential-backoff adapter with finite delay and automatic reset for the current single-process runtime. Before multi-instance API deployment, implement a shared durable adapter with the same port so attempts are coordinated across instances. Never use permanent account lockout as the primary control.

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
- **STD-SEC-001**
- **STD-SEC-003**
- **STD-SOFT-001**

## Consequences

### Positive
- Reduces attack surface
- Compliance with security standards

### Negative
- May impact user experience (MFA, session timeouts)
- Implementation and maintenance overhead

### Neutral / Risks
- Regular security audits required
- Key rotation and secret management complexity

## Alternatives Considered

| Alternative | Description | Pros | Cons |
|-------------|-------------|------|------|
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |
| Alternative | No description | (Add pros) | (Add cons) |

## Related Requirements

No directly related requirements documented.

## Related Decisions

- **8BXHCC2GBDHS6939MV0GTA4AR3**: Use versioned JCS snapshots and SHA-256 for authorization binding (accepted)
- **VVWYJKD93R4A9A7B5009H07F73**: Use provider-neutral local identity with opaque server-side sessions (accepted)

## Implementation Notes

### Suggested Implementation Steps

1. Define acceptance criteria
2. Create implementation plan
3. Implement with tests
4. Code review and merge
5. Update documentation


## Validation Criteria

- [ ] Decision reviewed by team
- [ ] Alternatives documented and evaluated
- [ ] Consequences understood and accepted
- [ ] Related requirements linked
- [ ] Implementation plan created
- [ ] Threat model updated
- [ ] Penetration test scheduled (if major change)
- [ ] Compliance requirements verified


---

*Generated by Skyhook Auto-ADR on 2026-10-07T10:19:33.133Z*
*Review and update before marking as "accepted"*
