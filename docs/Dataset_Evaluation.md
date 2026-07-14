# Dataset Evaluation — M11 Step 1.1 (Documentary Screen)

**Status: DOCUMENTARY SCREEN ONLY. No dataset is selected by this document.**

This is the M11 step 1.1 deliverable per the Version 2 Execution Plan. It compares candidate
replacement datasets for PaySim on paper, and nominates the top candidates to carry forward
into **M11 step 1.2 — the empirical gate**.

Nothing here constitutes a selection. Per the plan's governing rule:

> **A dataset is not selected until it has passed the V1 instrumentation: the leakage gate
> (permutation importance + ablation) and an account-recurrence check.**

---

## 0. Read this first — why a documentary screen cannot select a dataset

Both source documents state that their preferred candidates have no known leakage:

- The five-dataset comparison, on IBM AML: *"We found **no documented leakage issues** in
  IBM AML."*
- The CaixaBank deep-dive: *"There is **no documented built-in leakage**"* and *"there is
  **no known dataset-originated target leakage**."*

**That is precisely the position we were in with PaySim before we trained on it.**

PaySim had no documented leakage either. It looked structurally ideal — accounts, balances,
counterparties, labels, direction — and it would have scored well on any comparison matrix,
including this one. Its two fatal properties surfaced only when it was *trained on and
interrogated*:

1. The cancellation leak — the simulator reverses fraudulent transactions, so balances
   encode the label. 98.5% of permutation importance landed in balance artifacts
   (`tfm-scorer-20260703224313_training_report.json`).
2. The single-account structure — ~99.85% of origin accounts appear exactly once. When the
   leak was fully removed (importance share 0.0%, ablation delta 0.0), behavioural PR-AUC
   was **0.3369** against a 0.50 floor (`tfm-scorer-20260704053632_training_report.json`).
   There was almost nothing underneath.

"No documented leakage" is a statement about **the literature**, not about **the data**. It
means nobody has looked, or nobody has published. It is not evidence of absence, and this
document treats it as exactly zero evidence either way.

Every claim below is therefore a **hypothesis to be tested in step 1.2**, not a finding.

### Provenance caveat on the source documents

Both source PDFs (`docs/dataset-research/five-dataset-comparison.pdf`,
`docs/dataset-research/caixabank-deep-dive.pdf`) are LLM-generated research summaries.
Their inline citation markers (`【97†L168-L172】` and similar) do not resolve to verifiable
sources. Several figures are explicitly hedged in the originals ("presumably", "likely",
"exact schema is undocumented", "unclear if transfers exist").

**Consequence:** every quantitative figure in the matrix below is **reported, not verified**.
Structural facts that determine our decision — row counts, per-entity recurrence, actual
column lists, fraud base rate — must be confirmed against the real dataset files during step
1.2. Do not treat this table as ground truth.

---

## 1. Comparison matrix

Scored against the plan's eight criteria. **Reported** figures, unverified.

| Criterion | **CaixaBank Tech 2024** | **FD Handbook (ULB)** | **IBM AML / TabFormer** | **IEEE-CIS** | **BankSim** | **Kaggle CC (ULB/Worldline)** |
|---|---|---|---|---|---|---|
| **Scale / fraud rate** | ~13.3M txns; ~0.15% | ~1.75–1.8M txns; ~0.7–0.8% | up to 180M txns; ~0.1% | 590,540 txns; ~3.5% | 594,643 txns; 1.21% | 284,807 txns; 0.17% |
| **Entity model** | client → card → merchant (MCC) | customer → terminal | account → account (multi-bank) | card (card1–6), no customer ID | customer → merchant | **none** |
| **Behavioural richness** | **High** — ~13.3M txns over the 2010s; profiles (income, debt, credit score), card limits, MCC, channel flags | **High** — 5,000 customers, 10,000 terminals, 183 days; explicit sequences | **High** — long simulated span, multi-hop flows, drift | Low–Med — repeat card usage, but no customer ID and anonymised time offset | Medium — 1,500 customers over 180 days, but single-hop only | **None** — no IDs, 2-day span |
| **Account recurrence** *(the V1-specific check; PaySim ≈ 0.15%)* | **High (reported)** — ~13.3M txns ÷ ~100k users ≈ **~133 txns/user** | **High (reported)** — ~1.8M ÷ 5,000 ≈ **~360 txns/customer** | **High** — accounts recur across banks by design | **Unusable** — no customer identifier; card1–6 are anonymised and inconsistent | Medium — 1,500 customers × 180 days | **Zero** — no identifiers at all |
| **Leakage risk** | *Claimed low* — no running balances. **Real risks:** temporal aggregation (a documented "home zip" leak from future data caused a performance spike); proxy variables (credit score strongly predicts the fraud label) | **Known artifacts by design** — rule-generated fraud, e.g. *all* transactions above \$220 are fraud in scenario 1; scenario 3 multiplies amounts by 5. A model can trivially learn the generator's rules | *Claimed low* — pre-transaction fields only, no post-event fields. Unverified | Low–Med — no simulator artifacts, but PCA features invite quirk-overfitting | **Medium** — documented artifact: `Category` strongly anti-correlated and `MerchantID` positively correlated with fraud; a model can shortcut on category | Low — but only because there is nothing to leak |
| **Feature interpretability** *(deciding criterion)* | **High** — income, debt, credit score, credit limit, MCC category, chip/swipe/online, amount, timestamp. All human-readable | **Medium** — six canonical fields (txn id, datetime, customer, terminal, amount, label). Readable but **thin**: no category, no profile, no merchant semantics | **Low–Med** — timestamp, from/to bank & account, amount, currency. Readable but **very thin**; no merchant, no category, no profile | **Very low** — 394 of 432 columns are PCA components (V1–V339). Explanations can only be statistical | Low — age, gender, zip, merchant category. Thin but readable | **Very low** — Amount + V1–V28 (PCA) only |
| **Fraud labels** | Synthetic, injected; separate label file; **train labels only** | Synthetic, rule-injected | Synthetic, generator-labelled (`IsLaundering`) | **Real** | Synthetic, injected | **Real** |
| **Temporal structure** | **Strong** — full datetimes, ~decade span, documented seasonality | **Strong** — full datetimes, 183 days | **Strong** — simulated timestamps over a long span | Weak — anonymised second-offset, no absolute date | Weak — coarse **day** index only | **None** — 2 days, no entity to attach time to |
| **Operational realism** *(can an analyst build a case?)* | **Good** — amount vs credit limit, amount vs income, MCC category, channel, client history. Supports evidence assembly | Medium — customer/terminal history supports lookup; but evidence reduces to "amount was high" / "terminal is bad" | Low–Med — alert-generation only; no merchant, no names, no context. Explanation is limited to graph patterns | **Poor** — flat classification set; "the model found patterns in PCA space" is the only available explanation | Low — minimal evidence (age, gender, merchant category) | **None** |
| **Entity-model compatibility with V1** | **Low** — customer-card-merchant, not peer-account-transfer. No balances, no beneficiary. §4 | **Low** — customer-terminal. No balances, no beneficiary | **Medium** — account→account transfers *do* map to V1's peer model, but there are no balances and no merchant | **Very low** — no account entity at all | **Low** — customer→merchant, no account-to-account | **None** |
| **Licence** | Apache 2.0 | GPLv3 (code) / CC | CDLA-Sharing 1.0 | Kaggle competition terms | CC BY | CC BY |

---

## 2. Reconciling the two recommendations

The two documents disagree:

| Source | Recommends |
|---|---|
| `five-dataset-comparison.pdf` | **IBM AML** as the core modelling dataset, **combined with IEEE-CIS** for card fraud; PaySim retained for demo |
| `caixabank-deep-dive.pdf` | **CaixaBank** — replace PaySim completely; PaySim retained for demo |

**For this product, CaixaBank is the better recommendation.** The five-dataset document's
recommendation is not wrong in general — it is wrong *for us*, and the reason is that it
optimises for modelling fidelity while our two hardest constraints are architectural.

The deciding criteria, per the brief, are **interpretable features** (the rule engine and the
explanation layer must be able to operate on them) and **genuine per-account history**. Judged
on those two, the five-dataset recommendation fails on both halves.

### Why the IEEE-CIS half of that recommendation is disqualifying

IEEE-CIS cannot be used by this product's architecture, and the source document says so
itself without drawing the conclusion:

- *"394 numeric 'V' features (PCA components)"* — **the rule engine cannot fire on a PCA
  component.** A `RuleHit` in this system carries the exact fields and thresholds that made
  it fire, so an analyst can judge it on its face. "V217 > 1.4" is not judgeable. It is not
  evidence; it is a coefficient.
- *"The only explanation possible is statistical ('this transaction was flagged by a model on
  hidden factors'), not narrative evidence."* — **the grounding gate has nothing to ground
  against.** The groundable evidence contract (invariant I-2) requires every claim in an
  explanation to trace to a named, readable evidence element. PCA components are not readable
  elements.
- *"there is no unique customer identifier linking transactions... building true customer
  histories is hard"* — **no account recurrence.** This is the *exact* failure that killed
  PaySim, arriving from the opposite direction: PaySim had an account ID with no history
  behind it; IEEE-CIS has history with no account ID in front of it. Either way there is no
  behavioural baseline.
- The document's own scoring puts IEEE-CIS at **Operational Realism: Low**, **Explainability:
  Low**, **Decision-Support Fit: Low (no context)**.

This is not a new finding. **V1's DDR-01 already rejected IEEE-CIS on precisely these
grounds** — interpretability and entity structure. Re-adopting it in V2 would reverse a
standing architectural decision in order to gain a model we could not explain, could not
write rules against, and could not ground. That is the opposite of what V2 is for.

### Why the IBM AML half is a product pivot, not a dataset swap

IBM AML is a genuinely strong dataset and it scores **High** on behavioural richness and
account recurrence — it clears the second deciding criterion comfortably. It fails the first.

- Its entire feature surface is *"timestamp, amount, currency, source/target bank and account
  IDs"*. The source document is explicit: *"No customer demographics or external metadata"*,
  *"no merchant data, device info, or geo-location"*, *"human-readable context is limited"*.
- Our evidence assembler must answer **seven evidence requirements** — what happened, why it
  was flagged in human terms, whether it is abnormal *for this account*, the broader pattern,
  direction and balances, the risk score, and the synthetic disclosure. On IBM AML, requirements
  2 and 4 collapse to "this account participated in a cycle." That is one signal, not a case
  file.
- The document rates it **Decision-Support Fit: Low–Med (alerts only)**.

More fundamentally: IBM AML's labels are `IsLaundering`. **Adopting it does not change our
dataset; it changes our product** — from transaction fraud monitoring to anti-money-laundering
monitoring. Different typology, different rules, different analyst, different regulatory
frame. That may be a fine product. It is not *this* product, and swapping it in under the
banner of "dataset replacement" would be a scope change smuggled in as a data decision.

Applying the plan's governing question — *what specific limitation of V1 does this address?* —
IBM AML addresses the account-recurrence limitation and then introduces a new one at least as
bad: an evidence surface too thin for the workspace, the rules, and the grounding gate to
operate on.

### Why CaixaBank wins on both deciding criteria

- **Interpretable features:** income, total debt, credit score, credit limit, card brand and
  type, MCC category, chip/swipe/online channel, amount, timestamp. Every one of these is a
  field a rule can fire on, an analyst can read, and the grounding gate can verify a claim
  against. *"An analyst can readily understand 'amount vs credit limit' or 'credit score' in
  an explanation."* Rules like *"amount is 4× this client's 90-day average in a first-seen MCC
  category"* are directly expressible — and, critically, **directly explainable**.
- **Genuine per-account history:** ~13.3M transactions with a stable `client_id` and `card_id`
  over a multi-year span — a reported ~133 transactions per user against PaySim's ~1. This is
  the single thing PaySim could not provide, and it is the thing the entire product is built
  around.

CaixaBank is the only candidate that clears **both** bars. That is the reconciliation.

### The catch, stated plainly

CaixaBank is **synthetic, undocumented, and un-peer-reviewed**. Its generation method is
explicitly *undisclosed*. The deep-dive rates "Synthetic Artifacts" as its **highest** risk
(*"fraud might only occur at specific MCCs or on specific days... risk of overfitting to
simulation bias"*), and flags that credit score strongly predicts the fraud label — which,
depending on how the generator injected fraud, could be a proxy leak of exactly the PaySim
kind, or could be a legitimate risk factor. **Nobody knows which, because nobody has trained
on it and ablated.**

An undisclosed generator with an injected fraud label is *structurally the same class of
object as PaySim*. The fact that it has no *balance* columns rules out PaySim's specific leak;
it rules out nothing else. This is why CaixaBank is a **candidate**, not a selection.

---

## 3. Top two candidates for the empirical gate (step 1.2)

| Rank | Candidate | Why it goes forward | What the gate must falsify |
|---|---|---|---|
| **1** | **CaixaBank Tech 2024** | The only candidate clearing both deciding criteria: interpretable features *and* genuine per-account history. | Is the reported ~133 txns/user real? Does `credit_score` / `income` carry implausible permutation importance (a proxy leak)? Is fraud concentrated in a narrow MCC set (a generator artifact)? Does behavioural performance survive ablation of the profile features? |
| **2** | **Fraud Detection Handbook (ULB)** | Clears both bars, more weakly: readable fields and strong customer/terminal recurrence (~360 txns/customer), with a fully open, documented generator — the one thing CaixaBank lacks. | It carries **known, documented rule artifacts** (`TX_AMOUNT > 220 → fraud`). This makes it a **deliberate calibration case**: our gate *should* detect them. If the gate does not flag a dataset whose leak is published in its own documentation, the gate is broken — and that is worth knowing before we trust it on CaixaBank. |

**Reserve: IBM AML**, if and only if both of the above fail the gate *and* the project accepts
the product pivot to AML typologies described in §2. It is ranked third here despite the
five-dataset document ranking it first — the disagreement is deliberate and the reasoning is
in §2.

**Rejected at the documentary screen** (will not be gated): **IEEE-CIS** (PCA features; no
customer identifier — architecturally unusable, and already rejected by DDR-01), **Kaggle
CC/ULB** (no identifiers, 2-day span, PCA — zero account recurrence by construction),
**BankSim** (documented category/fraud correlation artifact; day-granularity timestamps;
single-hop; superseded by FDHB on every axis).

### The outcome the gate is allowed to reach

If **both** top candidates fail the leakage gate or the account-recurrence check, the honest
response is **another documented exclusion**, not a softened gate and not a fallback to the
best of a bad set. The gate does not bend to keep the roadmap moving. Per the plan, that
outcome is a finding, not a failure.

---

## 4. The entity-model cost — this is the real price of Phase 1

**Every leading candidate is customer-card-merchant. V1 is peer-account-transfer.** This is
not a schema detail; it invalidates part of the product's rule layer, and it must be budgeted
explicitly.

### V1 rules under a card-merchant entity model

| V1 rule | Reads | Fate under CaixaBank / FDHB | Why |
|---|---|---|---|
| `account_draining` | `frac_bal_orig_moved`, `orig_account_emptied` | **Cannot exist.** Delete or re-derive. | Both candidates have **no running balances**. There is no origin balance, so there is no fraction of it to move. The rule is not weakened — its input fields do not exist. |
| `mule_passthrough` (defined, not enabled) | inbound-then-outbound peer legs | **Cannot exist.** | Card datasets have **no account-to-account transfers**. The deep-dive is explicit: *"multi-leg laundering and mule networks are not simulated."* The activation path documented in IC-M3-01 becomes moot — there is no inbound leg to assemble. |
| `new_beneficiary_large` | `is_new_counterparty`, `amount` | **Re-derivable.** | "Beneficiary" becomes "merchant" or "MCC category". Becomes *large amount at a first-seen merchant / first-seen category for this client*. Semantics shift; the shape survives. |
| `velocity` | `txn_count_24h` | **Survives.** | Transaction count in a trailing window is entity-agnostic. The only candidate rule that transfers unchanged. |

**One of four rules survives intact. One is re-derivable. Two cease to exist.**

### What replaces them

The card-fraud typologies the new entity model *does* support, and which the V1 rule set has
no equivalent for:

- **Card testing** — a burst of small-value authorisations on a card (velocity, re-tuned).
- **Stolen-card / CNP** — high-value online (`is_online`) spend deviating from the client's
  channel baseline.
- **Amount-vs-capacity anomaly** — transaction amount against `credit_limit` or
  `annual_income`. This is genuinely new, has no V1 analogue, and is highly explainable.
- **Category deviation** — spend in an MCC the client has never used.
- **Geographic anomaly** — *not available.* Neither candidate carries transaction location
  (CaixaBank has a coarse user `region` only). Budget it out.

### The cascade — where the cost actually lands

1. **Canonical Evidence Schema** — the entity model changes from
   `account → counterparty` to `client → card → merchant`. The schema spine
   (`schema/entities.py`, `schema/evidence.py`) is re-modelled. Per the architectural
   principle, the canonical schema is not *bent* to accommodate a dataset — it is
   deliberately re-derived, once, and everything conforms to the new one.
2. **Evidence assembler** — the seven evidence requirements are re-sourced. Requirement 5
   ("direction and balances") **has no source** in a card dataset and must be re-specified,
   not silently dropped.
3. **Rule engine** (`rules/definitions.py`) — two rules deleted, one re-derived, a new
   card-typology family authored. `config/rules.yaml` is rewritten.
4. **Feature pipeline** — and note the invariant: **point-in-time correctness is
   property-tested per distinct traversal mechanism** (IMP-005). A card dataset introduces
   *at least two* new traversals — per-`client_id` and per-`card_id` — and each one needs its
   own invariant-level property test that fails when the traversal reads a future row. This is
   non-negotiable and it is a real cost line.
5. **Explanation layer** — templated copy is rewritten around card-fraud language.
6. **Demo/seed data** — the curated demo cases are PaySim-shaped and must be rebuilt.

**This cascades into M12 and M13 and it is the true cost of Phase 1.** It is not a reason to
avoid the change — V1's dataset cannot support the product, and that is settled. It is a
reason not to pretend the change is cheap.

**What does *not* change** (the architecture holds): layer separation, the `Scorer` interface,
the absent-score recommendation path, the grounding gate, the append-only audit, the
reconstruction guarantee, the governance-config discipline, and the leakage gate itself.

---

## 5. Gaps and concerns

1. **Sparkov / Kartik2112 was never evaluated.** The V2 plan names it explicitly as a
   candidate (1.85M transactions, 1,000 customers, 800 merchants, clear-text features) and
   **neither PDF covers it**. On the two deciding criteria it looks strong on paper: clear-text
   interpretable features and ~1,850 transactions per customer. It is a live omission, not a
   rejection. **Recommendation:** screen it before locking the step-1.2 candidate list; it may
   displace FDHB as candidate #2.

2. **The plan's list and the PDFs' list do not match.** The plan names IBM AML/TabFormer,
   IEEE-CIS, Sparkov, BankSim, CaixaBank (+ optional FD Handbook). The PDFs cover IBM AML,
   IEEE-CIS, BankSim, Kaggle CC, FD Handbook, CaixaBank. Net: **Sparkov missing; Kaggle CC
   added** (and Kaggle CC is trivially rejected). Six datasets are evaluated here, satisfying
   the plan's "at least five", but not the plan's *named* five.

3. **CaixaBank provides training labels only.** `train_fraud_labels.json` covers the training
   set; no test labels are published. This directly affects the out-of-time evaluation design
   and must be resolved in step 1.2 — an out-of-time split may have to be carved from the
   labelled portion alone. **This could be disqualifying and needs checking early.**

4. **CaixaBank's user count is unverified.** The ~133 txns/user figure depends on an
   *assumed* ~100k users ("presumably large... tens or hundreds of thousands"). If the real
   figure is nearer a million users, recurrence drops toward ~13/user — still far better than
   PaySim, but a materially different dataset. **This is the single most important number to
   verify first**, because it is the criterion PaySim failed.

5. **The credit-score / fraud correlation is unresolved.** Reported as a realism *feature*
   (*"poorer credit scores correlate with higher fraud rates"*). It is equally consistent with
   the generator having injected fraud *as a function of* credit score — in which case it is a
   proxy leak of exactly the PaySim kind, and the model would learn the generator, not fraud.
   **The ablation must specifically target the profile-feature family** (credit score, income,
   debt), the way V1's targeted the balance family. If behavioural performance collapses when
   profile features are removed, that is a FAIL.

6. **Responsible-AI note carried forward.** Both source documents flag that a credit-score →
   fraud dependence risks compounding socioeconomic bias. Neither candidate carries protected
   attributes, so V1's honest limitation (demographic fairness cannot be assessed, and no proxy
   is manufactured) **carries into V2 unchanged**. This should be stated in DDR-02.

---

## 6. What happens next

Per the plan, step 1.2 takes the top two candidates and runs them through the V1
instrumentation **before** either is committed to:

1. **Account recurrence, computed directly.** If most entities appear once, reject regardless
   of how good the dataset looks otherwise. (For CaixaBank: verify against the real files;
   concern §5.4.)
2. **Baseline scorer + full leakage gate** — permutation importance, ablation, verdict. The
   ablation delta is the primary determinant.
3. **Generator-artifact check** — does any single feature or feature family carry implausible
   importance? (For CaixaBank: the profile-feature family, specifically; concern §5.5.)

**Deliverable:** `docs/Dataset_Gate_Results.md` — the empirical evidence for the selection, not
the argument for it. Only then is DDR-02 written.

---

## Sources

| Document | Location |
|---|---|
| Five-dataset comparison (IBM AML, IEEE-CIS, BankSim, Kaggle CC, FD Handbook) | `docs/dataset-research/five-dataset-comparison.pdf` |
| CaixaBank deep-dive | `docs/dataset-research/caixabank-deep-dive.pdf` |
| V1 leakage evidence (baseline) | `evaluation/reports/tfm-scorer-20260703224313_training_report.json` |
| V1 leakage evidence (remediated / excluded) | `evaluation/reports/tfm-scorer-20260704053632_training_report.json` |
| V1 dataset decision (DDR-01) | `docs/internal/01_Product_Specification.md`, Appendix A |
| Point-in-time-per-traversal rule (IMP-005), mule activation path (IC-M3-01) | `docs/internal/IMPLEMENTATION_DECISIONS.md` |
| The V1 story this screen exists because of | `docs/V1_RETROSPECTIVE.md` |

---

*Documentary screen only. All figures are reported from the source documents and are
unverified against the datasets themselves. No dataset is selected until it passes the
empirical gate (M11 step 1.2).*
