# Transaction Fraud Monitoring — Hackathon Release Plan
**Release strategy layered on the approved roadmap · fixed 3-day window**
Lead AI/ML Engineer & Technical Architect

Authoritative references (not reproduced here): Product Specification, Implementation Plan, Engineering Addendum, completed M0. This document prioritises delivery against the deadline while preserving the approved architecture. The Implementation Plan remains the long-term engineering roadmap; this is a release strategy on top of it.

---

## 0. The constraint, stated plainly

A faithful Version 1 is ~22–34 developer-days (Implementation Plan §6). Roughly three developer-days are available. That is a real ~7–10× gap. **Implementation scope flexes; the architecture does not.** Wherever the submission departs from the full plan, the departure is explicit below and carries a backlog item.

---

## 1. Definition of Success (the anchor)

One end-to-end acceptance test defines success. A judge can clone the repository, run the documented setup, launch the app, and complete this loop on **real PaySim data** with no manual intervention or mocked user actions:

> **Triage Queue → Open Case → Review Assembled Evidence → Review Recommendation + Basis → Review Grounded Explanation (or deterministic fallback) → Record Disposition with Mandatory Rationale → Route the Case**

That loop is the product. All scope is derived backwards from it. A thinner product that completes the loop beats several polished components that never connect.

**The irreducible core (must work, or the submission fails):** ingest → score (real, gate-run) → assemble evidence + groundable set → recommend (deterministic) → templated explanation behind the grounding gate → disposition with mandatory rationale (engagement floor) → route → append-only audit, all surfaced through the Streamlit loop. Everything else is enhancement.

---

## 2. Vertical-slice principle and classification

Reduce scope, not architecture. Every retained layer participates in the loop, even where its implementation is deliberately minimal.

Four classes are used below:
- **Required** — essential to the acceptance loop.
- **Simplified** — real behaviour, reduced scope, architecture intact.
- **Stubbed** — minimal implementation **behind the real architectural interface**.
- **Deferred** — postponed to the post-hackathon roadmap (backlog §7).

**Hard rule on stubs (non-negotiable):** every stub sits behind its real interface. A stubbed Scorer returns through the real `Scorer` interface; a stubbed LLM sits behind the real `Explainer` interface. Nothing is hardcoded across a layer boundary. The interface, not the implementation, is the architectural commitment. This is what keeps the slice faithful rather than a quiet redesign.

---

## 3. Per-milestone release scope (M1–M10)

M0 is complete: schema models, migrations, config, logging, audit-writer scaffold, and the API/DI skeleton already exist, which shortens several milestones below.

| Milestone | Required | Simplified | Stubbed (behind interface) | Deferred → backlog | Traceability / why |
|---|---|---|---|---|---|
| **M1** Schema + ingestion | Real PaySim ingest into the canonical schema; point-in-time features; out-of-time split | Minimal-but-real interpretable feature set (fewest per family that score + populate evidence); ingest a curated PaySim subset | — | Full feature families; large-scale ingest | FR-1, §6.2, §6.5, §8.3. The loop needs real evidence and a real score; both derive from these. |
| **M2** Scorer + **leakage gate** | **Leakage gate: feature-importance + ablation + verdict (FIXED, does not flex)**; HistGB scorer via the real `Scorer` interface; core metrics (PR-AUC, precision, recall, ROC-AUC on OOT) | DF-1 as a single interpretable-vs-kitchen-sink comparison; probability calibration measured, applied only if time | — | Full bounded candidate comparison; calibration tuning; threshold sensitivity | FR-3/4/5/22/23/26, §9, DF-1. See fixed decision below. |
| **M3** Rule engine | Real `RuleEngine` interface with ≥2 real definitions (account-draining, mule pass-through — the PaySim-signature patterns) feeding recommendation + evidence | Enabled rule set in config reflects what ships | Velocity, new-beneficiary+large as no-op definitions behind the engine if referenced | The two deferred definitions (real logic) | FR-6/7. The layer participates with real, auditable hits on genuine PaySim fraud. |
| **M4** Evidence assembly | Assembler builds the Case answering the seven evidence requirements; **groundable set is real and complete** (the gate depends on it) | Evidence completeness scaled to the shipped feature set | — | Richer derived aggregates | FR-2. "Review Assembled Evidence" is in the loop; cannot be stubbed. |
| **M5** Recommendation policy | Deterministic (score band + rule hits) → clear/hold/escalate; borderline → hold; thresholds from config | Brief cost-justified default rationale | — | Full cost model + sensitivity analysis | FR-8/9, §11.2. "Review Recommendation + Basis" is in the loop. |
| **M6** Explanation | **Templated explainer (real) + deterministic grounding gate (real) + graceful fallback (real)** | Ungrounded rate reported (≈0 by construction on the templated floor) | **LLM path: documented stub behind the real `Explainer` interface** (upgrade to minimal single-provider only if time remains) | Full LLM prompt engineering; advanced grounding pipeline | FR-10/11/12/24, §3, §5.5. See fixed decision below. |
| **M7** Workspace + disposition + routing | Streamlit loop over the API: queue (visible ordering) → case (separable panels, drill-down, **no pre-selected disposition**, labelled AI text) → disposition (clear/hold/escalate, **mandatory rationale, engagement floor**) → routing (escalation carries the case; hold pends). No auto-execution | Minimal-but-faithful UI (functional, not polished); override is free (any non-recommended action is logged as deviation) | — | Search/filter (FR-19); UI polish | FR-13/14/15/16/17/18; NFR-4. This is the acceptance loop. Non-pre-selection verified supported (Addendum §1). |
| **M8** Audit + signals | Append-only audit record at disposition capturing the full per-case snapshot; decision reconstructable from the log; signals captured, not consumed | Single `disposition_recorded` event (sufficient for reconstructability) rather than multi-event granularity | — | Per-stage audit events | FR-20/21, NFR-3. Writer exists (M0); this wires real payloads. |
| **M9** Offline evaluation | Report the **leakage verdict**, core model metrics, and grounding rate as the submission's evidence; runnable from a script | Consolidation of artifacts produced in M2/M6 | — | Subgroup / false-positive-burden (FR-25); threshold sensitivity | §7, §8, FR-22/24/26. These are the strongest V1 evidence and feed the slides. |
| **M10** Integration + deploy | `docker compose up` (or documented setup) launches the app and completes the loop on real PaySim with no manual steps; graceful degradation verified (LLM off → templated) | Latency measured and reported (not tuned) | — | Hosted public demo | NFR-1/2/5. Integration is the acceptance test. |

### Two fixed milestone decisions

**M2 — Simulator-leakage gate does not flex.** Run it. If the selected model fails on balance artifacts and there is no time to remediate, ship with the failure documented, the ablation evidence presented, and remediation named as future work. A leaking model is never presented as production-ready because the deadline is close. Detecting and transparently reporting leakage is stronger engineering judgement and Responsible-AI practice than hiding it. This is the one place scope is fixed.

**M6 — Ship on the templated floor.** The architectural requirement is that no ungrounded claim reaches the analyst. The templated explainer, deterministic grounding gate, and fallback are real and Required. The LLM is a documented stub behind the real `Explainer` interface, upgraded to a minimal single provider only if time allows. This is the correct place to save time because the architecture already defines graceful degradation as the right behaviour.

---

## 4. Effort reality (honest)

Estimated for the slice above, assuming M0 is done and stack familiarity: M1 ~0.75d, M2 ~0.75d, M3 ~0.4d, M4 ~0.4d, M5 ~0.2d, M6 ~0.5d, M7 ~0.9d, M8 ~0.25d, M9 ~0.25d, M10 ~0.6d. **Total ≈ 4.5–5 developer-days.**

Against a three-day window this is still tight: even the faithful thin slice runs ~1.5–2 days beyond three. I am stating this rather than presenting a plan that looks faithful but cannot finish in time. **Flex order if behind schedule** (cut from the bottom, never the irreducible core or the M2 gate): defer the second rule (one real rule is enough to exercise the layer) → defer all M9 subgroup/sensitivity → keep the LLM stubbed → defer search → trim features to the minimum that scores and populates evidence → report latency as a single measured number. With those cuts the slice approaches the window; closing the remainder means long days or accepting one non-critical item as backlog. The loop and the leakage gate ship regardless.

---

## 5. Streaming-readiness: the abstraction point (Kafka / Redis)

Excluding Kafka and Redis for V1 is an **implementation decision driven by the current deployment context (a static PaySim dataset and a three-day window), not an architectural limitation.** The architecture is streaming-ready because downstream components depend on the **Canonical Evidence Schema and repository interfaces, never on the ingestion source or a cache.**

- **Ingestion is the seam for streaming.** `data/ingest.py` is a source adapter whose only contract is "produce canonical `Transaction` records into the store." The V1 batch file reader and a future Kafka consumer are two implementations of that same contract. Scoring, evidence assembly, recommendation, and explanation read from the canonical schema, so swapping batch → streaming changes only the ingestion adapter. No downstream component changes.
- **The persistence/repository layer is the seam for caching.** Reads (queue ordering, feature/evidence lookup) go through repository interfaces. A Redis cache is introduced transparently behind a repository implementation; callers use the same interface. No downstream component changes.

M0 already places these seams: ingestion is isolated, persistence sits behind models/repositories, and every layer imports `schema/`. V1 deliberately avoids the infrastructure while keeping the seams intact.

---

## 6. Submission artifacts plan (three deliverables)

**1. Public GitHub repository.**
- *Dataset preparation (M1):* an ingest/prepare script; a small committed curated PaySim sample for the demo, plus a documented full-PaySim download path for reproducing training/eval.
- *AI workflow (M2, M6):* the trained scorer + the leakage-gate run; the templated explainer + grounding gate + fallback.
- *Product logic (M3–M5, M7, M8):* rules, recommendation, workspace loop, append-only audit.
- *Evaluation artifacts (M9):* leakage verdict, core metrics, grounding rate emitted under `evaluation/reports/`, labelled measured-vs-modelled (§7).
- *Documentation:* README setup + the acceptance test; this plan; the backlog (§7); the controlled reference docs.

**2. Working demo.**
- The scorer is **trained offline and the model artifact committed**, so the judge does not retrain. `docker compose up` loads the pinned model, applies migrations, and **seeds real PaySim cases** from the committed sample (ingest → score → assemble → recommend → enqueue). The LLM is disabled by default, so the demo runs on the templated floor. The judge opens the workspace and completes the loop with no manual or mocked steps. This is exactly what M10 must make true.

**3. Presentation slides — evidence per milestone.**
- M1: canonical schema + why PaySim fits the entity/evidence model.
- **M2: core metrics + the leakage-gate verdict** (a headline: Responsible-AI practice and engineering judgement).
- M4/M5: evidence assembly + deterministic recommendation = the workflow value proposition.
- **M6: grounding gate + graceful degradation** = trust and the no-ungrounded-claim guarantee.
- M7: the workspace loop = the product.
- M8: auditability / reconstructable decisions.
- Throughout: the measured-vs-modelled framing (§7) so every number is honestly scoped.

---

## 7. Backlog (post-hackathon roadmap seed)

Every simplification, stub, and deferral, linked to its milestone and specification reference, so implementation resumes from a documented roadmap.

| # | Item | Class | Milestone | Spec ref |
|---|---|---|---|---|
| B1 | Full interpretable feature families | Simplified | M1 | §6.5 |
| B2 | Large-scale PaySim ingest (beyond demo sample) | Deferred | M1 | FR-1 |
| B3 | Full bounded candidate comparison | Simplified | M2 | FR-3, FR-22 |
| B4 | Probability calibration + threshold sensitivity | Simplified/Deferred | M2 | FR-23 |
| B5 | Velocity + new-beneficiary+large rules (real logic) | Stubbed/Deferred | M3 | FR-6 |
| B6 | Richer derived evidence aggregates | Deferred | M4 | FR-2 |
| B7 | Full cost model + sensitivity for thresholds | Deferred | M5 | FR-9, §11.2 |
| B8 | Real single-provider LLM explainer (then advanced grounding) | Stubbed | M6 | FR-10, V2 roadmap |
| B9 | Search / filter over transactions | Deferred | M7 | FR-19 |
| B10 | Workspace polish | Deferred | M7 | NFR-4/6 |
| B11 | Per-stage audit events | Simplified | M8 | FR-20 |
| B12 | Subgroup / false-positive-burden analysis | Deferred | M9 | FR-25 |
| B13 | Hosted public demo | Deferred | M10 | NFR-5 |
| B14 | Kafka ingestion adapter / Redis cache behind existing seams | Deferred | M1/persistence | §5.2, NFR-8 |

If the M2 gate fails without time to remediate: **B15 — model remediation (feature curation / model change), failure and evidence shipped in the submission (§3, M2).**

---

*Hackathon Release Plan — for review. No implementation proceeds until this is approved. The approved Implementation Plan remains the long-term roadmap; this plan preserves its architecture while fitting the three-day window.*
