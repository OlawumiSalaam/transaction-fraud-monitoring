# Implementation Decision Log

This document records implementation-specific engineering decisions made during development of the **Transaction Fraud Monitoring** product.

The product architecture and functional behaviour are governed by the approved design documents. This log records engineering choices made while implementing that design. It does **not** redefine or modify the approved architecture.

---

# Governing Documents

The following documents remain the authoritative source of truth, in order of precedence:

1. Product Specification
2. Engineering Addendum
3. Hackathon Release Plan
4. Long-Term Implementation Plan

If an implementation issue cannot be resolved without changing one of these documents:

- Stop implementation.
- Raise an **Implementation Concern**.
- Do not silently reinterpret the design.
- Do not record architectural changes in this file.

---

# Purpose

This log exists to record engineering decisions that:

- preserve the approved architecture,
- affect implementation,
- are likely to influence future development,
- should be understandable months after the project is completed.

Typical examples include:

- technology selection,
- library selection,
- deployment decisions,
- serialization formats,
- API conventions,
- implementation strategies,
- engineering trade-offs,
- infrastructure choices.

Routine coding decisions, bug fixes, refactoring, formatting, and minor implementation details belong in Git history—not here.

---

# Decision Record Template

Every implementation decision should follow this structure.

## ID

IMP-XXX

## Date

YYYY-MM-DD

## Title

Short descriptive title.

## Status

Proposed | Approved | Superseded

## Context

Describe the implementation problem or constraint that required a decision.

## Decision

Describe what was decided.

## Rationale

Explain why this approach was selected.

## Alternatives Considered

List the main alternatives and why they were rejected.

## Impact

Describe the parts of the system affected.

## Specification Traceability

List the relevant references, for example:

- FR-15
- NFR-4
- §5.5
- Principle: Human in the Loop
- Principle: Canonical Evidence Schema
- M7

---

# Decision Log

---

## IMP-001

**Date**

2026-07-03

**Title**

Streamlit selected as the Version 1 analyst workspace

**Status**

Approved

### Context

The original implementation plan proposed a server-rendered interface using Jinja2 and HTMX.

Given the fixed three-day hackathon delivery window, a faster implementation approach was required without changing the approved product architecture.

### Decision

Use **Streamlit** as the Version 1 analyst workspace.

All business logic remains behind the REST API.

Streamlit functions only as the presentation layer and consumes the backend APIs.

### Rationale

This minimizes frontend engineering effort while preserving:

- architectural layer separation,
- human-in-the-loop decision making,
- interface boundaries,
- future replaceability of the presentation layer.

The presentation technology changes.

The architecture does not.

### Alternatives Considered

**Jinja2 + HTMX**

Rejected for Version 1 because it increases implementation effort without improving the behaviour evaluated by the hackathon.

### Impact

Affected components:

- Analyst Workspace
- UI Layer

Unaffected components:

- Fraud Scoring
- Rule Engine
- Evidence Assembly
- Recommendation Policy
- Grounding Gate
- Audit Log
- REST API
- Persistence
- Data Pipeline

### Specification Traceability

- Engineering Addendum
- Hackathon Release Plan
- M7
- Principle: Layer Separation
- Principle: Human in the Loop

---

## Future Decisions

Additional implementation decisions will be recorded here as they are approved.

Examples may include:

- LLM provider selection
- Model serialization strategy
- Container deployment decisions
- API versioning strategy
- Data storage optimizations
- Streaming integration strategy (Kafka)
- Caching strategy (Redis)
- Model registry implementation