# Transaction Fraud Monitoring

Product Specification — Version 1 Design Record

*The definitive, implementable design record — decisions with their reasoning preserved.*

Consolidated across Product Foundations, Strategy, Reference Architecture, Data Strategy, and Specification.

Product design record · 30 June 2026

**Contents**

1\. Introduction and Purpose 

2\. Product Foundations 

3\. Architectural Principles 

4\. Product Strategy 

5\. Reference Architecture 

6\. Data Strategy 

7\. Measured vs. Modelled 

8\. Evaluation Strategy 

9\. Simulator Leakage Gating Result 

10\. Bias and Fairness Assessment 

11\. Decision Frameworks 

12\. Product Specification 

13\. Traceability Summary 

**Appendix A — Dataset Decision Record (DDR-01)** 

> *Addendum A — Multi-dataset (hybrid) evaluation* 

**Appendix B — Foundational Decision Gate** 

**Appendix C — Consolidated Assumption Log** 

## 1. Introduction and Purpose

This document is the definitive Version 1 design record for a Transaction Fraud Monitoring product. It consolidates a phased design into a single specification an engineering team can implement from, while preserving the reasoning behind each decision. It is written to be explainable as well as implementable: every major requirement traces back to a product principle, the reference architecture, the data strategy, or a formal decision record.

The "why" is kept visible in the body — each significant decision states its reasoning and the principal alternative that was rejected — and the full decision records are retained in the appendices. Two topics that tend to disappear during consolidation, the **Measured vs. Modelled** distinction and the **Simulator Leakage Gating Result**, are preserved as prominent standalone sections because they are central to the product's credibility and Responsible AI position.

#### The product in one paragraph

The product is a **case investigation workspace** that helps a frontline fraud analyst disposition flagged transactions faster, more consistently, and more defensibly. For each flagged transaction it produces a risk score, applies deterministic rules, assembles the evidence behind the alert, generates a grounded plain-language explanation with a recommended action, and records the analyst's decision while keeping every consequential decision under human control. AI supports the decision; it never makes it.

#### How to read the traceability tags

Requirements and decisions carry short tags to their source: **\[P:…\]** a product principle; **\[A:…\]** a reference-architecture component or property; **\[D:§…\]** a data-strategy section; **\[2:…\]** a Phase-2 core decision; **\[DF:…\]** a decision framework; **\[DDR\]** the dataset decision record; **\[RAI\]** a Responsible AI constraint.

## 2. Product Foundations

### 2.1 Vision

*A fraud operation where every alert is dispositioned quickly, consistently, and defensibly — where analysts spend their expertise on judgement rather than on assembling context, and where AI amplifies that judgement without ever replacing it.* The vision names the change in how analyst time and judgement are spent and how far the resulting decisions can be trusted — not "better scores," which is only a capability.

### 2.2 Mission

Give fraud analysts a workspace that assembles the evidence behind each alert, presents a grounded and explainable risk assessment with a recommended action, and keeps every disposition under human control.

### 2.3 Value Proposition

For frontline fraud analysts drowning in alerts, this is decision-support that compresses the time and uncertainty between an alert and a defensible disposition — assembling the context, explaining the risk in plain language, and recommending an action, while leaving the decision with the analyst. **The differentiation is against the two alternatives this market usually offers:** unlike a black-box scorer, which produces more alerts but no help deciding, and unlike a monitoring dashboard, which offers visibility but no decision, it improves the decision itself — transparently and auditably. The institution's value is consistency, auditability, throughput, and reduced operational risk without ceding control to automation.

### 2.4 Users

**Primary user: the frontline fraud analyst** (Tier-1 / Tier-2 case reviewer), who owns the clear / hold / escalate disposition. Every decision in this specification is anchored to this single user.

- **Senior analysts / investigators** — receive escalations; the assembled case travels with the escalation so it is not rebuilt from scratch. Not the daily user.

- **Fraud operations manager / team lead** — oversight of throughput, quality, and consistency; a consumer of aggregate outputs (mostly Version 2). Explicitly not the primary user — that is the rejected dashboard-as-product path.

- **Model governance / risk & compliance** — need auditability, evidence of grounding, and fairness assurance; consumers of the audit trail, not interactive daily users. A governance owner also sets operating-point thresholds.

- **The customer** — an affected party rather than a user, protected indirectly by keeping a human in the loop so legitimate transactions are not wrongly actioned.

### 2.5 Core User Problem

Reconstructing context and producing a consistent, defensible decision under time pressure, for every alert. The cost of the status quo is concrete: minutes of manual assembly per case across a deep queue; decisions that vary by analyst, time of day, and fatigue; and thin audit trails because the rationale lives in the analyst's head. The problem is the workflow, not the absence of a score.

### 2.6 Jobs To Be Done

**Functional:** when an alert lands, help me understand what happened and why it was flagged without digging through systems; when I am unsure, give me the evidence to judge it; when I make a call, help me produce a record that holds up to review; when the queue is deep, help me stay fast and consistent.

**Emotional:** reassure me I am neither missing real fraud nor wrongly flagging a legitimate customer; reduce the stress of a high-stakes call under time pressure. 

**Social:** let me justify my decisions to my manager, to auditors, and to regulators, and be seen as accurate and consistent. 

The emotional and social jobs are why transparency and auditability are load-bearing rather than decorative.

### 2.7 Product Goals

- Reduce time-to-disposition per alert.

- Increase decision consistency across analysts and over time.

- Improve the defensibility and auditability of decisions.

- Hold or improve detection quality — never trade away caught fraud for speed.

- Keep every consequential decision under human control.

- Earn and sustain analyst trust, so the tool is used rather than bypassed.

- **(Future Roadmap)** Enable continuous improvement of fraud detection through analyst feedback and operational outcomes. The learning loop is deferred; Version 1 is nonetheless instrumented from the start to capture dispositions, overrides, and outcomes as latent signals.

The goals are written to constrain one another: without "hold detection quality" and "trust/adoption" as explicit goals, a tool could hit its speed target by encouraging rushed rubber-stamping, or be quietly ignored. They must be read together.

### 2.8 Guiding Hypothesis

The product's guiding hypothesis is that **analyst time and decision consistency are the binding constraint** on fraud-operations quality — a strong framing for Version 1, but not assumed universal, since model maturity, staffing, fraud volume, and data quality shift the bottleneck between organisations. This is why the product is instrumented to observe where time and inconsistency actually accumulate, rather than asserting it.

### 2.9 Product Principles

- **Human judgement at the centre** — AI amplifies, never replaces; every consequential decision is the analyst's.

- **Trust through transparency** — the analyst can always see and verify the basis for any recommendation.

- **Visible boundaries** — deterministic logic, model output, generated text, and human judgement stay distinguishable.

- **Grounded by default** — no generated claim without traceable evidence.

- **Graceful degradation** — the product remains fully functional without the LLM.

- **Solve the workflow, not just the score** — optimise the decision loop, not model metrics alone.

- **Earned complexity** — prefer the simplest design that solves the operational problem.

## 3. Architectural Principles

These five named principles operationalise the product principles into enforceable architectural rules. They are stated explicitly so they survive into implementation as principles rather than becoming implied properties scattered through the document.

**Canonical Evidence Schema.** The product owns a single canonical evidence schema. Every component — the data pipeline, feature engineering, rule engine, machine-learning model, grounding layer, case view, and audit log — operates on that same schema. New datasets may be introduced only if they can either conform to the canonical schema without loss of meaning, or remain isolated as separate-purpose evaluation datasets. The canonical schema is never compromised to accommodate an additional dataset.

> *Why* — grounding and auditability depend on one stable, interpretable schema: every LLM claim must trace to a known field, every rule operates on known fields, and the case view assembles a known evidence shape. This is the deeper lesson behind the dataset decision record. *Enforced by* — the entity model (§6.2) and DDR-01 with its addendum (Appendix A). **\[A:Evidence assembly\]\[DDR\]**

**Human-in-the-Loop Decision Making.** The human analyst is the sole decider at the disposition step. Every AI and policy output is advisory; the analyst accepts, edits, or overrides it and records the rationale. Nothing consequential is executed by the system.

> *Why* — the only place decision support changes an outcome is where AI output, human judgement, and a consequential action meet; judgement must remain human for correctness and accountability. *Enforced by* — the Disposition component, recommendation-as-input, and the audit log. **\[A:Disposition\]\[P:human at the centre\]\[2:Decision C\]**

**No Automated Blocking or Denial of Service.** The product supports operational decision-making only. It must never automatically deny service, block a customer, or make a final financial decision. Clear / hold / escalate execute as routing, never as a financial action.

> *Why* — a Responsible AI and regulatory requirement; automation of an irreversible-adjacent action is unacceptable in this domain. *Enforced by* — the deterministic Routing component and the advisory recommendation policy. **\[RAI\]\[A:Routing\]**

**Grounding Verification.** Every factual statement in any generated narrative must trace to a model output, a deterministic rule hit, or a data field. Unsupported statements are detected and prevented from reaching the analyst.

> *Why* — hallucination in a financial-crime context is a real harm; the LLM must render evidence, never invent it. *Enforced by* — the Grounding Gate, the constrained evidence set, and the offline grounding-verification component with an ungrounded-rate acceptance criterion of ≈ 0 (§8, FR-11, FR-24). **\[A:Grounding gate\]\[P:grounded by default\]**

**Graceful Degradation.** The LLM improves the experience but is never required for function. A deterministic templated explanation, derived directly from the evidence, is always available. When the LLM is unavailable or its output fails the grounding check, the product falls back to the templated explanation and the workflow remains fully usable.

> *Why* — the LLM must not be a single point of failure; an outage or a hallucination should degrade fluency, not function. This also de-risks the highest-risk assumption in the design. *Enforced by* — the templated-explanation pathway and the fallback trigger (FR-12, NFR-2). **\[A:fallback\]\[P:graceful degradation\]**

## 4. Product Strategy

### 4.1 Product Form

**The product is a case investigation workspace** composed of two surfaces — a triage queue (entry) and a case view (decision surface) — and nothing else in Version 1. The unit of work is a case, and the product is the loop of pick up case, understand, decide, record, next case. **The workspace includes an operational overview as its entry point:** a prioritised work queue whose purpose is to route the analyst into individual cases, deliberately not a monitoring dashboard whose purpose terminates in display.

*Why this form* — it matches how analysts work (a queue, case by case) and makes the output types physically separable on screen, which is how "what the model said," "what the LLM wrote," and "what the analyst decided" stay distinct for audit. *Rejected alternatives* — a **conversational copilot** (inverts the effort, hides the system's reasoning behind a chat veil, and dissolves the layer boundaries the design requires) and a **monitoring dashboard as the product** (serves oversight and terminates in display; a richer analytics dashboard is a separate, mostly manager-facing Version 2 surface). **\[A:Triage queue, Case view\]\[2:Product form\]**

### 4.2 User Journey

The analyst moves through six stages, each mapped to a Job To Be Done. **Triage** — survey the queue and select the next case (stay fast and consistent). **Orient** — the case opens with evidence assembled (understand without digging). **Assess** — weigh the risk assessment, the explanation, and, when in doubt, the raw signals (get the evidence to judge it). **Decide** — select a disposition (the right call under pressure). **Justify** — record the decision with a rationale (defensibility to manager, auditors, regulators). **Route** — clear closes, hold pends, escalate hands on. The emotional and social jobs concentrate in Assess, Decide, and Justify, which is why drill-down and rationale capture are load-bearing.

### 4.3 End-to-End Workflow

The operational loop: (1) **ingest and evaluate** — the transaction is scored and independently checked by the rules, neither overriding the other silently, both preserved as evidence; (2) **assemble** the case (push, not pull); (3) **recommend** via a deterministic policy over the score band and rule hits; (4) **explain** via the LLM or templated fallback, behind the grounding gate; (5) **triage and open** — the case enters the queue at a configurable-policy priority; (6) **assess and decide** — the analyst reviews, drills down, and selects a disposition (not pre-selected); (7) **justify and record** — rationale captured; disposition, evidence shown, recommendation, chosen action, and explanation pathway logged; (8) **route and loop** — routing only; escalations carry the case; the disposition is captured as a latent learning signal.

### 4.4 Core Product Decisions

**A — Deterministic recommendation policy over the score.** The recommendation (clear / hold / escalate) is produced by a transparent deterministic mapping of score band plus rule hits to a suggested action. The LLM never scores and never decides.

> *Why* — it creates four crisp, auditable boundaries: the model produces a score, a deterministic policy turns it into a recommended action, the LLM produces an explanation, and the human decides. *Rejected* — a learned policy that selects the action directly: opaque, blurs the model/decision boundary, harder to audit, and edges toward the model deciding. **\[A:Recommendation policy\]\[2:Decision A\]**

**B — Configurable, transparent queue ordering.** The queue is ordered by a configurable operational policy that defaults to risk but may incorporate case age, SLAs, linked investigations, customer impact, or organisational policy; the ordering basis is visible and re-sortable. Ordering is an operational decision, not a property of the model score.

> *Why* — scarce analyst time should meet the highest-risk work first, but which factors define "first" belongs to the deployment. *Rejected* — FIFO (spends expertise on arrival order) and hidden automated routing (the analyst cannot see why this case, now). **\[A:Triage queue\]\[2:Decision B\]**

**C — Recommendation presented as input, never pre-selected.** The recommendation and its basis are shown prominently, but the disposition control is not pre-filled; the analyst must actively choose.

> *Why* — the primary structural defence against automation bias; a one-click pre-selected action invites disengaged rubber-stamping, which would let the product hit its speed goal by destroying decision quality. *Rejected* — pre-selecting the recommended action for speed (optimises the wrong goal). **\[P:trust\]\[2:Decision C\]**

**D — Rationale proportionate to governance needs.** Every disposition requires a rationale, and the depth of capture is proportionate to the governance needs of the decision. The specific graduation policy — whether driven by consequence, deviation from the recommendation, organisational policy, regulatory requirement, or a combination — is deferred to the governance and implementation phases.

> *Why* — rationale serves audit defensibility and anti-automation-bias engagement, both best served where the decision is consequential; uniformly heavy capture taxes routine clears and produces rote rationales. *Rejected* — rationale only on overrides (thin audit trail) and uniformly mandatory substantive rationale (friction and rote). **\[2:Decision D, refined\]**

**E — Supporting decisions from settled principles.** Escalations carry the assembled case; hold creates a pending state with a reason and optional follow-up; the analyst can always drill from any summarised or explained element to the raw signal; generated narrative is labelled as AI-generated and visually distinct from model and rule output.

> *Why* — these follow directly from the trust and visible-boundaries principles; their existence is settled, their exact form is implementation. **\[P:trust, visible boundaries\]**

### 4.5 AI Strategy

At runtime the components compose as: rules and score (independent) → evidence assembly → deterministic recommendation → grounded explanation → analyst. Three strategic commitments sit on top. **The three-way separation** of score (ML), recommended action (deterministic policy), and explanation (LLM) is the organising principle, because it keeps the system auditable and the LLM non-authoritative. **Uncertainty propagates explicitly:** a borderline score defaults the recommendation toward hold and is surfaced; thin evidence lowers recommendation confidence and the explanation must say so; LLM uncertainty or a grounding failure triggers the templated fallback. **The LLM consumes evidence; it does not source it.**

### 4.6 Human-in-the-Loop Design

The analyst is the sole decider. Their controls: select a disposition; override the recommendation (frictionless, logged as signal, never penalised); drill into the underlying evidence; edit the generated narrative before it is recorded; and add a rationale. The product never executes a consequential action itself. The anti-automation-bias measures are structural, not exhortations: no pre-selected action, evidence visible before decision, proportionate rationale forcing engagement where it matters, and uncertainty surfaced rather than buried.

### 4.7 Responsible AI Decisions

- **No automated denial, blocking, or final decision** — every output is advisory; only routing executes. **\[RAI\]**

- **Disclosure** — AI and LLM usage is disclosed in-interface and generated text is labelled. **\[RAI\]**

- **Grounding + fallback** — every generated claim traces to evidence, gated, with templated fallback on failure. **\[A:Grounding gate\]**

- **Visible boundaries** — model, rules, LLM, and human outputs stay distinguishable on screen.

- **Auditability** — each case logs the evidence shown, the score, the recommendation, the disposition, the rationale, and the explanation pathway used. **\[A:Audit log\]**

- **Uncertainty disclosure** — borderline and thin-evidence cases are surfaced honestly.

- **Fairness and privacy** — addressed in §10 and §6.7; the scorer is assessed for subgroup effects, with human-in-the-loop and transparency as partial (not substitute) mitigations.

## 5. Reference Architecture

The reference architecture is technology-agnostic. It distinguishes six logical kinds of component, keeps their boundaries explicit, and separates the real-time operational path from the deferred learning path. It is the model that governs the data strategy and the specification: every dataset, feature, and evaluation decision maps to a component here.

### 5.1 The six layers and their boundaries

- **Data** — the transaction record, the assembled case record, and the queue. Inputs and artifacts, never logic.

- **Machine learning** — produces a score and the signals behind it. It never decides and never writes prose.

- **Deterministic logic** — the rule engine, the recommendation policy, the grounding gate and templated fallback, and routing. Every one is an auditable if-then, not a probabilistic step.

- **LLM** — turns assembled evidence into plain language. It never scores, never decides, and every claim is checked by the grounding gate before a human sees it; on failure the templated explanation takes its place.

- **Human** — the only component that decides. Everything upstream is advisory.

- **Audit** — records the evidence shown, the score, the rule hits, the recommendation, the disposition, the rationale, and the explanation pathway — without altering the flow.

### 5.2 Two paths, different timelines

The **online operational path** supports a real-time decision — everything from the incoming transaction to the routed disposition; it is synchronous and exists to get one case to a disposition. The **offline learning & monitoring path** supports future evaluation, calibration, model monitoring, governance, and retraining; it runs on a different timeline. Separating them keeps the operational workflow independent of capabilities that do not yet exist.

### 5.3 The audit log as bridge; capture without consumption

The **audit log is the bridge**: written by the online path in real time, read by the offline path. It is the durable record that connects the two without coupling them. **Version 1 captures learning signals but does not consume them;** the feedback into the operational path is deferred and shown explicitly so the future evolution is visible without allowing future capabilities to leak into the Version 1 design.

### 5.4 Reference architecture diagram

![Online operational path, audit log bridge, and deferred offline learning and monitoring path.](assets/reference-architecture.png "Conceptual reference architecture")

*Figure 1 — End-to-end logical flow. Solid outline: online operational path (real time). Dashed: offline learning & monitoring path (deferred in V1). The audit log bridges the two.*

### 5.5 Explanation generation: logical dependency, deferred timing

The diagram fixes one property of the explanation and deliberately leaves another open. **Fixed (architectural):** an explanation is generated and grounding-verified *before any analyst reads it* — the LLM explainer feeds the grounding gate, which feeds the case view, so a person never sees ungrounded generated text, and on a grounding failure the templated explanation takes its place. This dependency is a principle, enforced by the Grounding Verification principle in §3 and by FR-11.

**Deferred (implementation):** *when* that generation runs — eagerly, pre-computed for every queued case, or on-open, when an analyst selects a case — is an implementation decision, not an architectural one, and Version 1 does not fix it. The diagram places the explainer and grounding gate between the triage queue and the case view precisely to remain neutral on this: both strategies run the identical logical step and differ only in timing, so this position depicts the dependency at the point of consumption without asserting batch pre-generation. The trade-off to settle in deployment is concrete — eager generation gives instant display when a case is opened but spends generation on cases that may never be opened; on-open generation aligns cost with consumption at the price of a short per-case latency at open — and it is driven by measured cost and latency. Either way it does not affect triage, because the queue is ordered from the score and the recommendation, neither of which depends on the explanation. **\[A:LLM explainer, Grounding gate, Triage queue\]**

## 6. Data Strategy

The data strategy is derived in a fixed order: the information the product needs to support the analyst's workflow, then the entities and relationships that implies, and only then which datasets qualify. The available data does not shape the product; the product's information needs determine the data.

### 6.1 Information needs

Reading the seven evidence requirements as data demands: to answer *what happened*, transaction-level facts (amount, timestamp, type/channel, originating account, counterparty); to answer *why it was flagged* in human terms, those facts as **interpretable fields**, because the rule engine operates on real fields and the LLM may only ground claims in things a person can read; to answer *is this abnormal for this account*, the account's **prior transaction history**, linkable to a stable account identifier and time-ordered; to answer *the broader pattern*, **counterparty linkage** and **direction plus balances**; to produce a *risk score*, **labels**; and, by Responsible AI constraint, none of it may be real, identifiable customer data.

### 6.2 Entities and relationships (the canonical schema)

- **Transaction** — the core event: id, timestamp, amount, type/channel, direction, originating-account reference, counterparty reference, fraud label.

- **Account** — the entity whose behaviour is judged; a stable identifier so its transactions can be gathered and a baseline formed.

- **Counterparty / beneficiary** — the other side of a transaction, identified well enough to tell new from known and to spot concentration and pass-through.

- **Account behavioural profile** *(derived)* — aggregates over an account's own history; computed, not a source field.

- **Beneficiary relationship** *(derived)* — which counterparties an account has transacted with before, and the timing of funds in versus out.

The single most consequential structural requirement is **account-linked, time-ordered transactions with a counterparty** — without it there is no behavioural baseline, no velocity, no sequence, and no mule detection. This entity model is the canonical evidence schema named in §3.

### 6.3 Dataset recommendation

**Recommendation: PaySim**, a synthetic mobile-money simulator, as the single Version 1 core dataset. It carries origin and destination account identifiers (counterparty linkage), transaction type and direction, balances before and after (pass-through and account-draining signals), a time step, and a fraud label — a near-direct match to the required entities, and contextually apt for the transfer/wallet/mobile-money channels the brief names. Among the realistic candidates evaluated it is **the most appropriate schema-compatible option**: the card-purchase simulators (BankSim, Sparkov) are customer-to-merchant with no account balances and no peer-account transfers, so mule and rapid-fund-movement patterns are structurally inexpressible in them. The full structured comparison and the multi-dataset (hybrid) evaluation are retained in Appendix A (DDR-01 and Addendum A).

*Rejected alternatives* — the anonymised public sets (ULB credit-card PCA features; IEEE-CIS) are disqualified on the interpretability and entity criteria: PCA/masked features give no account identifier, no counterparty, and nothing a rule or an explanation can be grounded in. A **hybrid / merged** training set is rejected on architecture grounds (schema fragmentation; dataset-provenance leakage), and **synthetic augmentation for training** is rejected as near-circular; the legitimate multi-dataset value (external-validity and demographic-fairness testing) is routed to Version 2 as a separate-purpose track. **\[DDR\]\[A:Canonical Evidence Schema\]**

### 6.4 Synthetic data as a design decision

Synthetic data is chosen deliberately, not as a fallback. **What it buys:** exactly the entity structure interpretable evidence and rules require; native satisfaction of the "no confidential or identifiable customer information" constraint rather than anonymisation-after-the-fact; controllability of pattern coverage; and reproducibility for independent verification. **What it costs, and the risks:** the representativeness gap (synthetic patterns reflect the simulator's assumptions, not real adversarial diversity); clean, complete labels that make any evaluation optimistic; the specific and serious risk of the model **learning the simulator** (balance-update artifacts can nearly separate fraud on their own — see §9); and the absence of demographic attributes, which constrains fairness assessment (§10).

**Disclosure to users** (a brief requirement): the product discloses that it is trained and evaluated on synthetic data; that reported performance is measured on synthetic distributions and is a modelled estimate of real-world performance, not a production result; and that the model has not been exposed to real fraud diversity.

### 6.5 Feature strategy

**Prefer interpretable, behaviourally-grounded features, computed point-in-time.** A feature here has three consumers — the scorer (predictive signal), the rule engine (auditable fields), and the evidence/LLM layer (human-readable "why") — so a black-box feature that is predictive but unreadable is disqualified even if accurate, because it cannot be grounded. This trade-off is governed by the framework in §11.1. Feature families derive from the entity model: transaction-intrinsic; account-behavioural over trailing windows; counterparty (new-beneficiary, distinct-count, concentration); and balance/sequence (fraction of balance moved, account emptied, inbound-then-rapid-outbound).

Two leakage cautions are first-class, not implementation trivia. **Temporal leakage:** features use only information available at the transaction's timestamp, and the split is **out-of-time** (train earlier, test later), never random. **Simulator leakage:** the balance-consistency artifacts are treated as suspect and validated against (§9). Both are reasons the evaluation is read as modelled, not literal. **\[D:§6\]\[A:Rule engine, Fraud scoring\]**

### 6.6 Data limitations

A single dataset means a single context and limited external validity; PaySim's fraud typology is narrow (chiefly transfer/cash-out draining), so some target patterns — dormant-account reactivation in particular — are weakly represented (resolved in §12, FR-7); clean labels make evaluation optimistic; the short (~31-day) span limits any assessment of seasonality or drift; the absence of demographic attributes limits fairness assessment; and the simulator-learnability risk caps how far any metric can be trusted as a real-world indicator.

### 6.7 Privacy considerations

Synthetic data satisfies the "no confidential or identifiable customer information" constraint by construction — no real PII, no re-identification risk. The Version 1 principle is data minimisation: ingest only the fields the workflow needs. The privacy questions that arise in a real deployment — the audit log holds sensitive case data, requiring retention limits and access control — are real-deployment concerns, noted and deferred (NFR-7). Introducing any real dataset later triggers a privacy review, which is part of why the hybrid is a Version 2 decision. **\[D:§9\]**

## 7. Measured vs. Modelled (first-class)

This distinction is central to the product's credibility and Responsible AI position and is preserved as a standalone section. Under the Version 1 design constraint — no access to a production fraud team, real analysts, or organisational baseline data — results are reported in three explicit categories, and the boundaries between them are never blurred.

#### Measured (on synthetic data)

- Model metrics: PR-AUC, precision, recall (primaries), ROC-AUC (secondary).

- Probability calibration (reliability, Brier score).

- Grounding integrity (ungrounded-statement rate) and templated-fallback rate.

- Online-pipeline latency.

- Subgroup performance on available segments (type, amount band, activity level).

#### Modelled estimates (reasoned, not observed)

- Real-world detection performance (synthetic-to-real transfer).

- Cost-optimality of the chosen thresholds (depends on assumed costs).

- Any Version 1 time-to-disposition figure.

- Real-world group fairness (no protected attributes available).

#### Not measurable in Version 1 — deployment-instrumented only

- Analyst adoption and trust.

- Real time-to-disposition, decision consistency, and throughput.

- Real fraud outcomes (which arrive late and incomplete even in production).

Rule of record: no metric that requires production users or real outcomes is claimed as Version 1 evidence; where a baseline cannot be measured, a transparent, reasoned proxy is used and labelled a **modelled estimate**, distinct from **measured** results. No evidence that would require production access is invented or simulated. **\[D:§10,§11\]**

## 8. Evaluation Strategy

The architecture's online/offline split organises the evaluation, because the two paths answer different questions and are measurable to very different degrees under the no-production-access constraint.

### 8.1 Online operational path

*Does the product support the real-time decision?* Evaluated through expert and heuristic means, not fabricated user metrics: a cognitive walkthrough of the case view against the seven evidence requirements, simulated analyst workflows, and system-behaviour measurement — chiefly end-to-end latency of the assemble → score → recommend → explain pipeline, which is measurable. Product-Outcome metrics (time-to-disposition, consistency, trust, throughput) remain deployment-instrumented and not Version 1-claimable.

### 8.2 Offline evaluation pipeline (first-class components)

- **Model evaluation** — PR-AUC, precision, recall (primaries, given imbalance), ROC-AUC (secondary), on the out-of-time split, comparing the bounded candidate set and selecting honestly. Measured on synthetic; a modelled estimate of real performance.

- **Operating-point calibration** — two senses. *Probability calibration:* reliability diagram and Brier score, with isotonic or Platt scaling if needed. *Threshold selection:* the score bands the recommendation policy maps to clear/hold/escalate, framed governance-first (§11.2, FR-9) — a cost model justifies the defaults and sensitivity analysis shows how they move, without claiming an objectively correct operating point.

- **Grounding verification** — define the groundable evidence set per case; constrain the LLM to it; run a programmatic post-check that every number and entity reference in the narrative appears in that evidence set; on failure, fall back to the templated explanation. Metric: ungrounded-statement rate (target ≈ 0) plus fallback rate. One of the few things genuinely measurable in Version 1 without real users, because on synthetic cases the evidence is known.

- **Subgroup / bias analysis** — false-positive-burden analysis across available segments (§10), run as a standing part of the pipeline.

### 8.3 Data splits

Out-of-time for model and calibration; a held-out case sample for grounding and explanation; and strict point-in-time feature computation so no test information leaks into features. Drift detection and longitudinal monitoring are built to plug in but not run — instrumented now, consumed later, consistent with the offline path being deferred. **\[D:§10\]**

## 9. Simulator Leakage Gating Result (first-class)

Because the measured AI-System-Health metrics are the strongest empirical evidence available in Version 1, the risk that a model achieves impressive metrics by exploiting PaySim's bookkeeping artifacts — rather than genuine behavioural fraud signals — sits directly beneath the product's credibility. This validation is therefore elevated from an internal diagnostic to a **reported, gating result**.

#### The question the specification must answer

*How did we establish that the model is learning behavioural fraud patterns rather than simulator artifacts?* The answer is produced by three steps and a documented conclusion:

- **Feature-importance inspection** — confirm that behavioural features (velocity, deviation from the account's baseline, counterparty and sequence signals) carry the predictive signal, not the balance-consistency artifacts.

- **Ablation** — retrain with the balance-artifact features removed and report the performance delta. A model whose performance collapses without the artifacts was exploiting them.

- **Documented pass/fail conclusion** — a stated verdict, reported alongside the headline metrics.

**This result gates model selection.** A model that only survives on artifacts fails eligibility (FR-4) regardless of its headline metrics (FR-26). The realism claim is stated in its defensible form: **PaySim provides the entity structure and behavioural patterns required to support the product's workflow, while Version 1 cannot establish how well those patterns represent real-world fraud behaviour.** **\[D:§6\]**

## 10. Bias and Fairness Assessment

Two kinds of bias are in scope, and honesty requires separating them. **Representativeness bias** — the synthetic distribution differs from real fraud — is addressed by the disclosures in §6.4 and cannot be closed without real data. **Group fairness** is where PaySim's lack of protected attributes bites: the product cannot directly assess demographic fairness in Version 1, and no proxy is manufactured to pretend otherwise.

What *is* assessable, and is a standing offline component, is **subgroup performance analysis** across the segments that exist — transaction type, amount band, account-activity level — to detect whether the model or rules systematically over-flag particular legitimate behaviours (a false-positive-burden analysis). The human-in-the-loop and the transparency of the case view are **partial** mitigations, explicitly not substitutes for a real fairness assessment; genuine protected-attribute fairness testing requires data deliberately not held and is routed to the Version 2 evaluation track (using a demographic-bearing simulator such as Sparkov, side-by-side, never merged). **\[D:§8\]**

## 11. Decision Frameworks

### 11.1 Interpretability trade-off, with its floor (DF-1)

The interpretable model is compared against a "kitchen-sink" model on the out-of-time synthetic evaluation, and the result is reported. The decision logic:

- *Negligible difference* → interpretable wins by default; parity is noted.

- *Meaningful but acceptable difference* → interpretable still wins; the performance cost is disclosed transparently as a documented limitation.

- *Reversal condition* → the commitment to interpretability is reconsidered only when the detection loss becomes large enough that the product would consistently deliver **well-explained but materially less reliable decisions** — i.e., when the interpretability gain no longer justifies degrading the core job of catching fraud without wrongly flagging legitimate customers. That is the point at which the trade-off reverses.

Two guards on the reversal: it requires **explicit governance sign-off**, never a silent switch; and it is **not free** — a less-interpretable model still cannot leak authority into the LLM (grounding holds), so reversing toward accuracy incurs a compensating explanation cost that is part of the decision. **\[P:trust\]\[A:LLM explainer, Grounding gate\]**

### 11.2 Governance-first thresholds

The clear / hold / escalate thresholds are **primarily a configurable governance decision with sensible defaults**. The cost model — the relative cost of a missed fraud, an analyst review, and a false escalation — *explains and justifies the defaults*, and the sensitivity analysis *shows how the defaults change under different assumptions*. It does **not** claim to discover an objectively correct operating point. A governance owner ultimately sets the thresholds; the product exposes them as a knob. Because the costs themselves are modelled assumptions, this is the defensible framing and it aligns with the governance philosophy throughout the design. **\[A:queue/policy as configurable\]\[P:human at the centre\]\[D:§10\]**

## 12. Product Specification

### 12.1 Functional requirements

#### Case formation

- **FR-1** Ingest transactions under the canonical entity model — transaction, originating account, counterparty, direction, balances, timestamp, label. *\[A:Transaction data\]\[D:§6.2\]*

- **FR-2** Assemble each case to answer the seven evidence requirements; push the assembled case, do not make the analyst pull. *\[A:Evidence assembly\]\[2:push-not-pull\]*

#### Scoring (machine learning)

- **FR-3** Score each transaction with a model selected from a bounded candidate comparison on the out-of-time split. *\[A:Fraud scoring\]\[D:§6\]*

- **FR-4** Selection is gated by the simulator-leakage validation (FR-26): a model that fails the gate is not eligible regardless of headline metrics. *\[D:§6,§9\]*

- **FR-5** Feature and model choice obey the interpretability framework (DF-1). *\[DF:1\]\[P:earned complexity\]*

#### Rules (deterministic)

- **FR-6** Deterministic rule engine for the Version 1-demonstrable patterns: velocity spikes, new-beneficiary + large amount, rapid in-and-out (mule pass-through), account-draining. Auditable if-then only. *\[A:Rule engine\]\[D:§6\]*

- **FR-7** The rule framework is extensible. **Dormant-account reactivation is classified out of the demonstrable scope of Version 1** — documented as a real indicator for future data that supports it, but not implemented or claimed in V1, because PaySim's fraud typology and thin per-account histories cannot validate it. No proxy is carried forward. *\[D:§6.6,§7\]*

#### Recommendation (deterministic policy)

- **FR-8** A deterministic policy maps score band + rule hits → clear / hold / escalate, advisory only; borderline / low-confidence defaults toward hold. *\[A:Recommendation policy\]\[2:Decision A\]*

- **FR-9** Thresholds are primarily a configurable governance decision with sensible defaults. The cost model explains and justifies the defaults; sensitivity analysis shows how they move; it does not claim an objectively correct operating point. A governance owner ultimately sets them. *\[A:policy configurable\]\[P:human at the centre\]\[D:§10\]*

#### Explanation (LLM + grounding + fallback)

- **FR-10** The LLM renders the assembled case into a plain-language risk summary and a draft rationale; it consumes evidence, never sources it. *\[A:LLM explainer\]*

- **FR-11** A grounding gate verifies every claim (number, entity) traces to a model output, rule hit, or data field; unsupported output triggers fallback. **Ungrounded-statement rate ≈ 0 is a gating acceptance criterion.** *\[A:Grounding gate\]\[2:7.2\]*

- **FR-12** A deterministic templated explanation is always available; the workflow is fully functional without the LLM. *\[A:fallback\]\[2:7.1\]\[P:graceful degradation\]*

- **FR-13** Disclose in-interface: AI/LLM usage, generated-text labelling, and that the system is trained/evaluated on synthetic data whose metrics are modelled estimates. *\[D:§6.4\]\[RAI\]*

#### Workspace and decision

- **FR-14** Triage queue ordered by a configurable policy defaulting to risk; ordering basis visible; re-sortable. *\[A:Triage queue\]\[2:Decision B\]*

- **FR-15** Case view presents evidence, score, recommendation, and explanation with drill-down to raw signals; the recommended action is not pre-selected. *\[P:trust\]\[2:Decision C\]*

- **FR-16** Disposition control (clear / hold / escalate); the human is the sole decider; no consequential action is auto-executed. *\[A:Disposition\]\[RAI\]*

- **FR-17** Every disposition captures a rationale, proportionate to the governance needs of the decision (graduation policy deferred to governance/implementation). *\[2:Decision D\]*

- **FR-18** Override is always available, frictionless, never penalised, and logged as a quality signal. *\[P:trust\]*

- **FR-19** Search and filter over transaction records. *\[brief\]*

#### Audit and signals

- **FR-20** The audit log records, per case: evidence shown, score, rule hits, recommendation, chosen disposition, rationale, explanation pathway used, identity, timestamps. *\[A:Audit log\]*

- **FR-21** Learning signals are captured but not consumed (offline path deferred). *\[A:offline path\]*

#### Offline evaluation (first-class)

- **FR-22** Model evaluation: PR-AUC, precision, recall (primaries), ROC-AUC (secondary), on the out-of-time split. *\[D:§10\]*

- **FR-23** Calibration in both senses: probability calibration (reliability, Brier; isotonic/Platt if needed) and governance-first threshold selection per FR-9. *\[D:§10\]*

- **FR-24** Grounding verification measured (ungrounded rate, fallback rate) on held-out synthetic cases. *\[D:§10\]*

- **FR-25** Subgroup / false-positive-burden analysis across available segments (type, amount band, activity level). *\[D:§8\]*

- **FR-26 Simulator-leakage validation is a reported, gating result.** The specification explicitly answers how we established the model learns behavioural fraud patterns rather than simulator artifacts, via feature-importance inspection, an ablation with the balance-artifact features removed, and a documented pass/fail conclusion. A model that only survives on artifacts fails FR-4. *\[D:§6,§9\]*

### 12.2 Non-functional requirements

- **NFR-1 Latency** — the online pipeline (score → assemble → recommend → explain) completes within an interactive budget; latency is a measured V1 metric. *\[A:online path\]\[D:§10\]*

- **NFR-2 Reliability / graceful degradation** — full function with the LLM unavailable. *\[P:graceful degradation\]*

- **NFR-3 Auditability** — any decision fully reconstructable from the log. *\[A:Audit log\]*

- **NFR-4 Transparency** — evidence always inspectable; layer boundaries visible on screen. *\[P:trust, visible boundaries\]*

- **NFR-5 Reproducibility** — data preparation and evaluation are reproducible and shareable by a single developer. *\[D:§6.5\]*

- **NFR-6 Maintainability** — modular case-view panels, extensible rule and feature sets. *\[P:earned complexity\]*

- **NFR-7 Security / privacy** — data minimisation now; access control and retention on the audit store are real-deployment obligations, deferred (synthetic data in V1). *\[D:§6.7\]*

- **NFR-8 Scalability** — the design must not preclude higher volume; V1 need not meet production load.

### 12.3 User stories

- As an analyst, I want each flagged case to open with the evidence already assembled, so I can understand it without digging through systems. **\[JTBD: understand without digging\]**

- As an analyst, when I am unsure, I want to drill from the summary to the raw signals, so I judge the case myself rather than trusting a black box. **\[JTBD: get the evidence\]\[P:trust\]**

- As an analyst, I want a recommended action with its basis shown but not pre-selected, so I make an informed call rather than rubber-stamping. **\[JTBD: right call under pressure\]**

- As an analyst, I want my decision recorded with a rationale sized to its stakes, so it holds up to review without slowing routine clears. **\[JTBD: defensible record\]**

- As an analyst, I want the queue to surface the highest-risk work first, so a deep backlog does not degrade my decisions. **\[JTBD: fast and consistent\]**

- As a governance owner, I want to set the clear/hold/escalate thresholds and see the reasoning behind the defaults, so operating points reflect our risk appetite. **\[FR-9\]**

- As a compliance reviewer, I want every decision reconstructable from the log, so I can audit after the fact. **\[NFR-3\]**

### 12.4 MVP scope and “good enough”

Version 1 is the MVP set: the workspace, the queue, the evidence-assembled case view, a **gate-passing** scorer from a bounded comparison, the demonstrable rule set, templated + grounded-LLM explanation, uncertainty display, mandatory-proportionate rationale, disposition + audit, override, search, and the offline evaluation pipeline. **"Good enough" for Version 1** (under the no-production-access constraint): the product demonstrably assembles context and produces evidence-grounded, trustworthy assessments; the scorer passes the simulator-leakage gate; grounding integrity is measured at ≈ 0 ungrounded; and detection quality is reported honestly as a modelled estimate on synthetic data. Deliberately **not** in V1: automated decisions, manager analytics, conversational query, and anything in the offline path's consumption.

### 12.5 Future roadmap

**Version 2:** natural-language query; manager analytics dashboard; override analytics; richer behavioural profiling; a Sparkov-based external-validity and demographic-fairness track (separate-purpose, never merged); advanced grounding-verification pipeline. **Future:** production drift monitoring; the retraining / active-learning loop (closing the deferred feedback arrow); network / link analysis for mule structures; multi-analyst collaboration and escalation routing; case-management / regulatory integrations.

### 12.6 Risks

- **Simulator leakage** (highest credibility risk) — the model exploits balance artifacts. *Mitigation:* the gating result of §9 (FR-26); eligibility gate (FR-4).

- **Synthetic → real transfer** — strong synthetic metrics may not hold. *Mitigation:* measured-vs-modelled labelling (§7); disclosure (FR-13); V2 external-validity track.

- **Grounding failure / hallucination** — a fabricated claim reaches an analyst. *Mitigation:* grounding gate + templated fallback (FR-11, FR-12); ≈ 0 gating.

- **Automation bias** — analysts rubber-stamp. *Mitigation:* structural — no pre-selected action, evidence-before-decision, proportionate rationale (FR-15, FR-17).

- **Threshold miscalibration** — defaults wrong for a deployment. *Mitigation:* governance-owned, sensitivity-analysed, configurable (FR-9).

- **Interpretability cost** — meaningful accuracy left on the table. *Mitigation:* the DF-1 framework, cost disclosed, reversal gated.

- **Fairness gap** — no demographic testing on PaySim. *Mitigation:* disclosed limitation; subgroup analysis (FR-25); V2 fairness track.

### 12.7 Assumptions (settled and updated)

- **Realism claim (softened):** PaySim provides the entity structure and behavioural patterns required to support the product's workflow, while Version 1 cannot establish how well those patterns represent real-world fraud behaviour.

- **Dormant reactivation:** resolved as out of Version 1 demonstrable scope (FR-7); no proxy carried forward.

- **Threshold defaults:** modelled, cost-justified, sensitivity-tested, configurable — not claimed as optimal (FR-9).

- **Interpretability floor:** defined by DF-1's reversal condition.

The full, numbered assumption log is retained in Appendix C.

### 12.8 Technical considerations

*The design is settled; these follow from it, and implementation remains open.* A scoring model family suited to tabular, imbalanced data with feature interpretability; a deterministic rules module over the shared interpretable feature substrate; an LLM invoked with constrained, evidence-scoped prompting plus a programmatic grounding post-check; a case/queue interface with modular panels; an append-only audit store; and reproducible data-preparation and evaluation notebooks. Specific libraries, frameworks, and deployment choices are not settled here.

## 13. Traceability Summary

Every major requirement traces to a product principle, the reference architecture, the data strategy, or a decision record. Requirement-level tags appear inline throughout §12; the table below summarises the load-bearing links.

| **Requirement / decision**                   | **Traces to**                                                                       |
|----------------------------------------------|-------------------------------------------------------------------------------------|
| **Case investigation workspace (form)**      | Product form decision; “solve the workflow, not the score” principle                |
| **Evidence assembly (FR-2)**                 | Seven evidence requirements; Evidence assembly component; Canonical Evidence Schema |
| **Deterministic recommendation (FR-8)**      | Core Decision A; visible-boundaries principle; No Automated Blocking                |
| **Recommendation not pre-selected (FR-15)**  | Core Decision C; trust principle; automation-bias risk                              |
| **Grounding gate + ≈ 0 rate (FR-11, FR-24)** | Grounding Verification principle; grounded-by-default; Decision 7.2                 |
| **Templated fallback (FR-12)**               | Graceful Degradation principle; Decision 7.1                                        |
| **Human sole decider (FR-16)**               | Human-in-the-Loop principle; RAI constraint                                         |
| **Routing, no auto-block (FR-16, routing)**  | No Automated Blocking principle; RAI constraint                                     |
| **PaySim single dataset (FR-1)**             | Information needs → entity model; Canonical Evidence Schema; DDR-01 + Addendum A    |
| **Interpretable features (FR-5)**            | Interpretability framework DF-1; trust principle                                    |
| **Simulator-leakage gate (FR-4, FR-26)**     | Data strategy §6/§9; measured-vs-modelled credibility                               |
| **Governance-first thresholds (FR-9)**       | Framework §11.2; policy-as-configurable; human-at-the-centre                        |
| **Auditability (FR-20, NFR-3)**              | Audit log component; auditability RAI decision                                      |
| **Captured-not-consumed signals (FR-21)**    | Offline path; audit-as-bridge; continuous-improvement goal (deferred)               |

## Appendix A — Dataset Decision Record (DDR-01)

**Decision required:** select the Version 1 core dataset. **Method:** score three realistic synthetic candidates — PaySim, BankSim, Sparkov — against the product's information requirements, not against availability or popularity. **Candidates chosen** because they produce labelled, entity-structured, interpretable transactions; the anonymised public sets (ULB-PCA, IEEE-CIS) were disqualified earlier on the interpretability and entity criteria and are not re-litigated here.

#### Evaluation criteria (from the information needs)

| **ID** | **Criterion — why it is a requirement**                                                                                       |
|--------|-------------------------------------------------------------------------------------------------------------------------------|
| **C1** | Account linkage (stable id, gatherable history) — behavioural baseline; “abnormal for this account”                           |
| **C2** | Counterparty identification (peer / beneficiary) — new-beneficiary, concentration, pass-through                               |
| **C3** | Interpretable fields usable by both rule engine and LLM — rules operate on real fields; LLM grounds only in readable evidence |
| **C4** | Direction + balance — mule accounts and rapid fund movement                                                                   |
| **C5** | Behavioural-history support — per-account baselines over time                                                                 |
| **C6** | Fraud labels — trainable scorer                                                                                               |
| **C7** | Channel fit — the brief's transfer / wallet / mule emphasis                                                                   |
| **C8** | Suitability for the evidence model — the seven evidence requirements as a whole                                               |

**Assessment (● strong · ◉ partial · ○ absent)**

| **Criterion**                                    | **PaySim**     | **BankSim**   | **Sparkov**        |
|--------------------------------------------------|----------------|---------------|--------------------|
| **C1 Account linkage**                           | ●              | ●             | ●                  |
| **C2 Counterparty (peer / beneficiary)**         | ● peer accts   | ◉ merchant    | ◉ merchant         |
| **C3 Interpretable fields (rules + LLM)**        | ●              | ●             | ● richest          |
| **C4 Direction + balance (mule / rapid)**        | ● both-side    | ○ none        | ○ none             |
| **C5 Behavioural-history support**               | ◉ thin         | ●             | ● richest          |
| **C6 Fraud labels**                              | ●              | ●             | ●                  |
| **C7 Channel fit (transfer / mule)**             | ● mobile-money | ◉ card/POS    | ◉ card/online      |
| **C8 Evidence-model suitability**                | ●              | ◉             | ◉                  |
| **Secondary: demographic attributes (fairness)** | ○ none         | ● age, gender | ● gender, job, dob |

**Trade-offs.** The discriminating rows are C2 and C4. PaySim's origin/destination accounts are peer accounts with balances on both sides and typed transfers, so beneficiary anomalies, pass-through (mule) chains, and account-draining are directly expressible. BankSim and Sparkov are card-purchase simulators — customer-to-merchant, one-directional, no account balances — so mule and rapid-fund-movement patterns are structurally inexpressible (C4 absent) and the counterparty is a merchant, not a beneficiary account (C2 partial). Where the card sims lead is behavioural-history richness (C5) and the secondary fairness axis (they carry demographics; PaySim does not). Between them, **Sparkov strictly dominates BankSim**; BankSim is essentially dominated and is retained here only to demonstrate the comparison was run systematically.

Choosing PaySim trades away behavioural-history richness and demographic fairness testing in exchange for the ability to express the transfer / mule / rapid-movement / beneficiary-anomaly patterns central to the brief and the evidence model. The fairness gap does not reverse the decision, because a card simulator would allow demographic fairness testing on a model that cannot demonstrate its primary detection patterns at all — the worse outcome. The gap is disclosed as a Version 1 limitation and is the reason a Sparkov-based fairness-and-external-validity track is the natural Version 2 addition.

**Conclusion — recommend PaySim.** The decisive criteria (C2 peer counterparty, C4 direction + balance) are prerequisites for the fraud patterns the product must detect and explain, and no card simulator can express them; interpretability (C3) and evidence-model fit (C8) are satisfied. The costs are explicit and disclosed. **PaySim is the settled Version 1 dataset.**

### Addendum A — Multi-dataset (hybrid) evaluation

The hackathon brief permits combining public datasets and extending public data with synthetic data. This addendum evaluates that permission as an architecture decision, against the entity model, feature strategy, evidence model, and workflow — not as a matter of what is available. The load-bearing constraint: the product's grounding and evidence model depend on one stable, interpretable schema (the Canonical Evidence Schema), so the real question is not “is more data better?” but “does a second dataset add signal the product needs without fracturing the single schema the whole product is built on?”

| **Dimension**              | **Merge into one training set**   | **Separate purposes (train vs. validate)** | **Extend PaySim w/ synthetic scenarios** |
|----------------------------|-----------------------------------|--------------------------------------------|------------------------------------------|
| **Schema compatibility**   | Broken — no compatible partner    | Preserved — each in its own schema         | Preserved by construction                |
| **Feature consistency**    | Inconsistent across schemas       | Same model can’t be computed on a card set | Consistent                               |
| **Interpretability**       | Degraded — two vocabularies       | Intact                                     | Intact                                   |
| **Grounding**              | Harder — schema forks             | Intact                                     | Intact                                   |
| **Engineering complexity** | High — reconciliation, imputation | Moderate — second pipeline                 | Moderate — generator + controls          |
| **Maintenance**            | High — two formats                | Moderate                                   | Moderate                                 |
| **Net effect**             | Weakens — reject                  | Clean, but evidentially weak in V1         | Weakens for training — reject            |

**Merge** is worst and fails on its own terms: with no schema-compatible partner it is necessarily cross-schema, forcing either the loss of the discriminating fields (balance + direction — the reason PaySim was chosen) or a sparse union in which the model can separate rows by which fields are populated — dataset-provenance leakage, the same failure family as simulator leakage. **Separate-purpose** is the architecturally right pattern but is blocked by availability: genuine external validation needs a real transfer dataset, and the real public sets are anonymised/PCA (no entity structure) while a card simulator tests transfer-trained features it does not contain — so it belongs in Version 2, framed honestly as methodology generalization, not real-world validation. **Extend with synthetic scenarios** for training is near-circular — authoring a pattern and then measuring the detector catching it undermines the very metrics that are the product's strongest V1 evidence — and is rejected; scripted cases as strictly-excluded workflow test fixtures are a QA artifact, not a data strategy.

**Recommendation — a single PaySim-based dataset remains the strongest Version 1 decision.** The combinable datasets do not move the needle on the product's actual limitation (synthetic-to-real representativeness), because none of them adds real, interpretable, entity-structured fraud data. Combining would add complexity that addresses a problem the product does not have while leaving the one it does have untouched. Against the standard held throughout — the smallest, most coherent solution that best serves the product — one dataset, one entity model, one feature substrate, one grounding vocabulary is that solution. The multi-dataset value is routed to Version 2 as a separate-purpose track with an explicit rule: **use additional datasets side-by-side for distinct purposes; never reconcile them into one training set, and never inject authored fraud into the measured set.**

## Appendix B — Foundational Decision Gate

The four load-bearing decisions that determine everything downstream, recorded here in brief. Their reasoning is expanded in §2–§4.

- **Primary user** — the frontline fraud analyst (case reviewer) who owns the clear / hold / escalate disposition. Rejected: the fraud operations manager (optimises for visibility, not decisions).

- **Core problem** — reconstructing context and producing a consistent, defensible decision under time pressure on every alert. Rejected: “reduce false positives” (a model-tuning objective, not a product).

- **Product form** — a case investigation workspace entered through a work queue. Rejected: a conversational copilot (inverts effort, dissolves boundaries) and a monitoring dashboard as the product (terminates in display).

- **Where the AI sits** — an ML scorer + deterministic rules + a grounded LLM explainer with a templated fallback, the human owning every verdict. Rejected: an LLM that scores or decides, and a conversational agent over everything (destroys auditability).

The reframing that underpins the gate: fraud scoring is a mature capability but not solved in any given deployment; the operational bottleneck is analyst triage, context reconstruction, and consistent decisions at scale. Model quality and workflow quality are complementary — the product improves both, with the decision workflow as its distinctive contribution.

## Appendix C — Consolidated Assumption Log

Each assumption records why it is reasonable, how it can be validated under the no-production-access constraint, and what changes if it proves false.

1.  **The information needs are correctly derived from the architecture.** Reasonable: they map one-to-one to the seven evidence requirements and the rule set. Validate by review. If false: the entity model is revised before any data work.

2.  **PaySim's schema satisfies the required entities.** Reasonable on inspection (accounts, counterparties, direction, balances, time, labels). Validate by schema check. If false: switch to a card/merchant simulator or augment.

3.  **Synthetic performance is an optimistic upper bound on real performance.** Reasonable given clean labels and simulator learnability. Validate only via real deployment (deferred). If false (worse transfer): real expectations lower; recalibrate.

4.  **Interpretable, behaviourally-grounded features carry sufficient signal.** Reasonable but untested. Validate by the interpretable-vs-kitchen-sink comparison on synthetic (DF-1). If false: an explicit interpretability-vs-accuracy cost exists, resolved per DF-1 and documented.

5.  **The relative-cost model for thresholds is a reasonable placeholder.** Reasonable as a starting point. Validate by sensitivity analysis now, real costs later. If false: thresholds shift — but they are configurable by design, so the product absorbs it.

6.  **Grounding can be verified to ≈ zero ungrounded rate at acceptable quality.** The highest-leverage assumption. Validate by direct measurement on held-out synthetic cases (measurable in V1). If false: lean harder on the templated path.

7.  **Subgroup analysis on available segments is a meaningful partial fairness proxy.** Reasonable given the data. Validate by expert review; real fairness needs protected attributes (deferred). If false: fairness assurance is weaker than hoped and is disclosed prominently.

8.  **Some target patterns (notably dormant reactivation) are under-represented in PaySim.** Likely true. Resolved by classing dormant reactivation out of V1 demonstrable scope (FR-7); no proxy carried forward.

9.  **The model learns behavioural fraud signal, not simulator artifacts.** Not assumed — established as a reported, gating result (§9, FR-26). If it fails the gate, the model is ineligible.
