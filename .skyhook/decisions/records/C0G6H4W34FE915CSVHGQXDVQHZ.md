# Decision: Evolve schemas through portable canonical packages and revision-guarded drafts

**ID**: C0G6H4W34FE915CSVHGQXDVQHZ
**Status**: accepted
**Category**: architecture
**Date**: 2026-10-08T06:54:19.216Z
**Author**: AI Agent + Human
**Governed Standards**: STD-ARCH-001, STD-ARCH-002, STD-SOFT-003

## Context

Evidentia needs import, export, comparison, and safe schema evolution without trusting package identity, rewriting immutable publications, or prematurely introducing a separate import aggregate.

**Project Type**: Web Application

**Profile**: web-app

**Relevant Tech Stack**:
- Identity: OIDC 



## Decision

Use the existing versioned canonical draft and publication JSON envelopes as portable packages. Inspect and validate packages before mutation, derive editable content while treating package identity and provenance as informational, preview deterministic compatibility against the current target, and apply only by creating a server-identified draft or replacing a tenant-owned draft at an expected revision. Preserve recognized extension definitions round-trip without activating providers. Record import/export actions through correlated structured events and existing idempotent command receipts; do not add persistence or automatically migrate records in this story.

This decision was made based on:

- Project requirements and constraints
- Team expertise and preferences
- Industry best practices
- Long-term maintainability



## Architecture Diagram

```mermaid
flowchart TB
    subgraph ArchitectureScope["🏛️ Architecture Scope: Evolve schemas through portable canonical packages and revision-guarded drafts"]
        direction TB
        Context["📋 Context / Ingestion"]
        Core["⚙️ Proposed Core Decision"]
        Outputs["🎯 Affected Components / Targets"]

        Context -->|"Applies To"| Core
        Core -->|"Governs"| Outputs
    end

    classDef default fill:#edf2f7,stroke:#718096,stroke-width:2px;
    classDef active fill:#e6fffa,stroke:#319795,stroke-width:2px,color:#234e52;
    class Core active;
```

## Architecture Mutation (Before vs After)

```mermaid
flowchart LR
    %% Architectural Mutation Visual Diff: Before vs After

    subgraph SubgraphBefore["⏮️ Current Architecture (Baseline)"]
        direction TB
        b_comp_client["Clients / Callers"]
        b_comp_current_pattern["Legacy / Existing Pattern"]
        b_comp_client --> b_comp_current_pattern
        b_comp_downstream["Downstream Resources"]
        b_comp_current_pattern --> b_comp_downstream
    end

    subgraph SubgraphAfter["⏭️ Proposed Target: Evolve schemas through portable canonical packages and revision-guarded drafts"]
        direction TB
        a_comp_client["Clients / Callers"]
        a_comp_new_pattern["Evolve schemas through portable canonical packages and revision-guarded drafts Implementation"]
        a_comp_client --> a_comp_new_pattern
        a_comp_downstream["Downstream Resources"]
        a_comp_new_pattern --> a_comp_downstream
    end

    b_comp_client -.->|"Evolution / Refactor"| a_comp_client

    %% Visual Diff Color Palettes
    classDef diffRemoved fill:#4c0519,stroke:#f43f5e,stroke-width:2px,color:#ffe4e6,stroke-dasharray: 4 4;
    classDef diffAdded fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5;
    classDef diffModified fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;
    classDef diffUnchanged fill:#1e293b,stroke:#475569,stroke-width:1px,color:#f1f5f9;
    class b_comp_client diffUnchanged;
    class b_comp_current_pattern diffRemoved;
    class b_comp_downstream diffUnchanged;
    class a_comp_client diffUnchanged;
    class a_comp_new_pattern diffAdded;
    class a_comp_downstream diffModified;
```

## Governing Standards

- **STD-ARCH-001**
- **STD-ARCH-002**
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

*Generated by Skyhook Auto-ADR on 2026-10-08T06:54:19.216Z*
*Review and update before marking as "accepted"*
