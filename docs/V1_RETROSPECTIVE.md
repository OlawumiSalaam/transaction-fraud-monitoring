# Version 1 — Retrospective

**How a fraud-detection model failed, why we excluded it instead of shipping it, and why
the product kept working.**

This is the engineering story of Version 1 of the Transaction Fraud Monitoring platform.
It is written to be read by someone who was not there.

Every number in it comes from a committed artifact under `evaluation/reports/`. Nothing is
estimated, inferred, or rounded for effect. Where a figure appears, the file it came from
is named.

---

## 1. What we set out to build

The premise was that fraud monitoring is a **decision-support problem, not a prediction
problem**.

A fraud analyst works a queue. For each flagged transaction they must reconstruct what
happened, judge whether it is abnormal for that account, weigh the signals, decide to
clear, hold, or escalate, and record a rationale that will survive scrutiny by a manager,
an auditor, or a regulator months later. A bare probability from a model helps with none of
those steps. It tells the analyst *that* something may be wrong — not *why*, and not *what
to do about it*. In a financial-crime context an unexplained score creates work rather than
removing it, because the analyst still has to assemble the context and defend the call.

So we built an **investigation workspace**, not a classifier. For each flagged transaction
the system assembles the supporting evidence, evaluates deterministic fraud rules, produces
an *advisory* recommendation, and generates a plain-language explanation that is verified
against the evidence before an analyst ever sees it. The analyst decides — always with a
structured rationale — and the system writes an audit record from which that decision can
later be reconstructed exactly.

The design philosophy was one line: **AI supports the decision; it never makes it.**

The ML scorer was one input to that system. An important one, and the one we expected to
carry a lot of the signal — but one input, behind an interface, among several.

---

## 2. Why governance came first

We built the governance layer before we had a model worth governing. The leakage gate, the
grounding gate, the append-only audit, the layer separation, the mandatory human
disposition — those went in early.

**It is worth being precise about why, because the obvious reading is the wrong one.**

We did not build them because we suspected the model would fail. We had no such suspicion.
We built them because *that is what a system which makes consequential decisions about
people's money should look like*. If your product can clear, hold, or escalate a customer's
transaction, then:

- an explanation that states something the evidence does not support is worse than no
  explanation, because it invites a confident wrong decision;
- a decision you cannot reconstruct months later is a decision you cannot defend;
- a model whose output you cannot inspect, override, or remove is a liability, not an
  asset;
- and the consequential act must belong to a human who can take responsibility for it.

None of that is contingent on the model being bad. It follows from the *domain*. So the
gates went in as a matter of course, the way you'd write tests — not as insurance against a
failure we were expecting.

Then the failure came, and the gates were exactly what caught it.

That is the honest sequence, and it is also the more useful one. If we had foreseen the
problem, the lesson would be "be smart enough to foresee your problems," which transfers to
nobody. The actual lesson is stronger and it transfers to everybody: **build this way even
when you believe your model is fine.** The discipline that lets you discover otherwise —
before your users do — is only there if you adopted it *before* you had a reason to.

---

## 3. The number that was too good

The interpretable primary model, trained on the full feature set, came back with a
**PR-AUC of 0.9983** on the out-of-time split.

*Source: `evaluation/reports/tfm-scorer-20260703224313_training_report.json`,
`candidate_reports[histgb_interpretable].metrics.pr_auc`.*

On a fraud problem with a **0.13% base rate**, that is not a plausible behavioural result.
Precision 1.0. Recall 0.9933. A near-perfect classifier on one of the hardest
class-imbalance problems in the field, produced by a pipeline that had been running for a
couple of days.

It is worth sitting with how this feels in the moment, because the feeling is the trap. A
number like that arrives as *success*. Everything in the pipeline was defensible —
point-in-time features, out-of-time split, preprocessing fit on the training fold only, a
fixed seed. Nothing was obviously wrong. The temptation to accept it, screenshot it, and
move on is real, and it is exactly what a deadline rewards.

We had a gate that ran automatically, so we didn't have to be virtuous. It ran, and it said
FAIL.

---

## 4. The investigation

The leakage gate (`evaluation/leakage_gate.py`) asks one question: **has the model learned
behavioural fraud patterns, or bookkeeping artifacts?** It answers with three strands of
evidence.

**Permutation importance — what is the model actually leaning on?**

Two features held essentially all of it:

| Feature | Permutation importance |
|---|---|
| `frac_bal_orig_moved` | 0.9689 |
| `orig_account_emptied` | 0.9606 |
| `amount` | 0.0271 |
| everything else | ≈ 0 |

The four balance-artifact features together held **98.5%** of total permutation importance.

**Ablation — how much performance survives without them?**

Remove the balance artifacts and PR-AUC collapses from **0.9983 to 0.3365** — an ablation
delta of **0.6626**.

**Verdict: FAIL.**

*All figures: `tfm-scorer-20260703224313_training_report.json`, `selected_leakage_verdict.evidence`
(`balance_artifact_importance_share: 0.9845…`, `pr_auc_delta: 0.6626…`,
`remaining_behavioural_pr_auc: 0.3365…`).*

**The cause was in the data, not the code.** PaySim cancels a fraudulent transaction after
flagging it — it reverses the money. The account balances therefore *encode which
transactions were fraudulent*. A model handed `frac_bal_orig_moved` and
`orig_account_emptied` can separate fraud almost perfectly by reading a bookkeeping
side-effect of how the simulator cleans up after itself. It never had to learn anything
about fraud.

This is the first lesson, and it is not a modelling lesson: **simulator leakage is a
property of the data-generating process.** The 0.9983 was produced by a careful pipeline.
No amount of modelling rigour would have caught it, because nothing about the modelling was
wrong. The defence was not a better model. It was an evaluation gate that treats a
too-good result as a hypothesis to be falsified rather than a milestone to be celebrated.

---

## 5. Remediation — and what it actually revealed

This is the part of the story that matters most, and it is the part that a compressed
retelling ("the model leaked, so we cut it") gets wrong.

**We fixed the leak. It worked.**

Remediation cycle 1 quarantined the four balance-artifact features from the primary model's
feature substrate entirely, and added behavioural features in their place
(`amount_to_prior_mean_ratio`, `amount_to_prior_max_ratio`, `hours_since_last_txn`).

The leak was gone. Completely:

| | Baseline `tfm-scorer-20260703224313` | Remediated `tfm-scorer-20260704053632` |
|---|---|---|
| Balance-artifact importance share | 98.5% | **0.0%** |
| Ablation PR-AUC delta | 0.6626 | **0.0** |

*Source: `tfm-scorer-20260704053632_training_report.json`,
`selected_leakage_verdict.evidence.balance_artifact_importance_share: 0.0`,
`pr_auc_delta: 0.0`.*

An importance share of exactly 0.0% and an ablation delta of exactly 0.0. The model was no
longer touching the simulator artifacts in any measurable way. By the standard that had
failed the baseline, the remediated model passed cleanly.

**And it failed anyway — on a different criterion.**

The gate's third strand is *remaining behavioural performance*: with the artifacts gone,
**is there any real signal left?**

There was almost none. The remediated model's behavioural PR-AUC was **0.3369**, against a
decision-support floor of **0.50**.

*Source: same artifact, `remaining_behavioural_pr_auc: 0.3369…`; floor from
`applied_defaults.min_behavioural_pr_auc: 0.5`.*

Note what that number is next to: the *baseline's* ablated performance was **0.3365**. We
removed the leak, added three behavioural features, and the honest behavioural performance
moved by **0.0004**. The new features contributed approximately nothing — permutation
importance of 0.0003, 0.00002, and 0.00002 respectively. The top signals in the clean model
were `amount` and the transaction-type one-hots. Not behaviour. Just *how much* and *what
kind*.

**This is the finding, and it is about the dataset, not the model.**

The leak was not hiding a weak model. **The leak was hiding an empty room.** Once we
removed the artifacts, there was nothing underneath — because the behavioural history the
product is built around does not meaningfully exist in PaySim. Approximately **99.85% of
PaySim origin accounts appear exactly once**. You cannot compute "is this transaction
abnormal *for this account*" when the account has no history. You cannot compute velocity,
cadence, dormancy, or deviation from a baseline that consists of a single row.

We had been trying to build a behavioural fraud model on a dataset that has almost no
per-account behaviour in it. The leakage discovery is what forced us to find that out.

**A note on what we did not do.** The obvious move at this point — the one a deadline
whispers — is to lower the floor. 0.3369 fails against 0.50; it passes against 0.30. The
threshold is a configurable default sitting in a YAML file. Nobody would have known.

We did not touch it. The project's fixed rule is that **the gate does not flex**, and a
threshold that moves to accommodate the result it is meant to judge is not a threshold. It
is decoration. Everything else in this document is worthless if that line is not held,
because a gate you are willing to move is a gate that never told you anything.

---

## 6. Why the scorer was excluded rather than shipped

Two failures, two cycles, one decision.

Under FR-4, a model that does not pass the leakage gate is **ineligible for operation**.
The remediated model did not pass. So it was excluded, and the exclusion was recorded in
the committed manifest as the headline of the evaluation, not as a footnote:

```json
"model_version_id": "tfm-scorer-20260704053632",
"leakage_verdict": "fail",
"scorer_eligible": false
```

*Source: `evaluation/reports/evaluation_manifest.json`.*

The evaluation summary leads with `SCORER INELIGIBLE — leakage gate verdict: FAIL`, placed
*inline with the metrics themselves*, so that the numbers cannot be read as a performance
claim by anyone skimming.

We could have shipped it. It would have been easy, and in a submission context it would
probably have gone unnoticed: a PR-AUC of 0.32 with a caveat buried in an appendix, or —
worse and simpler — the original 0.9983 with no caveat at all. That number would have
looked extraordinary on a slide.

Shipping it would have made the entire product a lie. Not a bug: **a lie.** The system's
one substantive claim is that it produces decisions a professional can defend. A scorer
that we knew was riding a simulator artifact, or that we knew had no behavioural signal,
feeding a recommendation that an analyst would rely on to decide about a customer's money —
that is the precise failure mode the product exists to prevent. We would have built a
machine for laundering an untrustworthy signal into a confident-looking recommendation.

So the failure shipped instead, documented, with the ablation evidence attached.

---

## 7. How the architecture absorbed the failure

Here is the thing we did not have to do when the model was excluded: **change any other
layer.**

Not the rule engine. Not the recommendation policy. Not the assembler. Not the explainer.
Not the grounding gate. Not the audit log. Not the workspace. Nothing.

The scorer had always sat behind a `Scorer` interface, and every downstream layer had
always consumed a *score status* rather than a model. So excluding it did not break the
system — it moved the system into an operating state it already knew how to be in:

- **The recommendation policy** switched to its absent-score path and ran on rule evidence
  alone. The path already existed, because the policy had always been written as a mapping
  from *(score status, rule hits)*, and "no score" was always one of the values that
  status could take.
- **The evidence assembler** emitted a `score_signal` element carrying the exclusion
  *reason* and no probability. The absence is represented *as evidence*, rather than papered
  over with a placeholder.
- **The grounding gate** then made a guarantee for free: since no score value entered the
  groundable set, any explanation asserting a score would fail grounding. The system cannot
  invent a score it does not have — not by discipline, but **structurally**.
- **The case screen** told the analyst the truth: model scoring is excluded by the leakage
  gate; this case is assessed on verified rule evidence.

This is what layer separation is *for*. It is not tidiness. In a system where the model
*is* the product, a leaking model is a terminal event — you ship it or you have nothing. In
a system where the model is one input behind an interface, a leaking model is **an
operating state**.

We did not design it that way because we saw this coming. We designed it that way because
it is the right way to build a system that makes consequential decisions. It is simply what
was waiting there when the failure arrived.

---

## 8. Why deterministic recommendations remained operational

With the scorer gone, the product runs on the rule engine — and the rule engine was never
touching the score in the first place (a property with its own test:
`test_engine_evaluate_is_independent_of_score`).

Three deterministic rules, each producing a `RuleHit` that carries the exact fields and
thresholds that made it fire: `account_draining`, `velocity`, `new_beneficiary_large`. An
analyst can read the evidence, see the threshold, and judge it on its face.

**There is a subtlety here worth naming, because it looks like a contradiction.** The rule
engine *legitimately reads the very balance features the ML scorer was forbidden to learn
from* — `account_draining` fires on `frac_bal_orig_moved`. Why is that acceptable?

Because **transparency, not the feature, is the deciding property.** A learned dependence
on a balance artifact is opaque: the model rides it invisibly, and nobody can see that its
apparent skill is bookkeeping. A hand-authored rule that says *"100% of the origin balance
moved in a single transaction, threshold 90%"* is inspectable. The analyst sees the signal,
sees the threshold, and decides how much it is worth. The rule is not claiming to have
learned anything about fraud. It is stating a fact and letting a human weigh it.

**And one thing the system will not do.** On the absent-score path, the policy **cannot
return `clear`**. It can escalate, it can hold — it cannot certify a transaction as safe.
Clearing is an assertion of low risk, and without a trustworthy score the system has no
basis on which to make that assertion. It may raise concern; it may not pronounce safety.

That asymmetry is deliberate, and it is enforced by a property test
(`test_absent_score_never_clears`). It is also the single most visible cost of the model's
exclusion — and the honest one to pay. A system that cannot clear is a system doing less
than it should. A system that clears without a basis is a system doing harm.

---

## 9. What PaySim structurally could not support

The dataset was chosen carefully and for defensible reasons. PaySim was the most
schema-compatible public option against the product's hardest requirement: account-linked,
time-ordered transactions with a counterparty. Without that entity model there is no
behavioural baseline, no velocity, no counterparty pattern — nothing for a rule to read or
an explanation to cite. On paper, PaySim provided all of it.

**On paper.** That is the whole problem.

What documentary evaluation could not reveal — and what only training on the data and
interrogating the result did reveal — were two structural properties:

1. **The cancellation leak.** The simulator reverses fraudulent transactions, so the
   balances encode the label. (§4.)
2. **The single-account structure.** ~99.85% of origin accounts appear exactly once. The
   per-account behavioural history the entire product is designed around **barely exists in
   the data**.

The second is the deeper one, and it is the one that caps everything. The behavioural
ceiling on this dataset is roughly **PR-AUC 0.34** — and that is not a statement about our
model. It is a statement about the data. `amount` and transaction type are essentially all
the signal there is, because per-account behaviour is essentially all the signal there
isn't.

PaySim also cannot support: dormant-account reactivation (no histories to be dormant),
mule pass-through detection (needs inbound-leg peer evidence the structure does not
provide), demographic fairness assessment (no protected attributes), and any drift or
seasonality analysis (~31 days of simulation).

We were, in the end, building a behavioural fraud product on a dataset with almost no
behaviour in it. That sentence is the entire brief for Version 2.

---

## 10. Lessons

**Build the governance layer before you need it — especially when you believe you don't.**
We did not build the leakage gate because we expected the model to fail. We built it
because it is what a consequential-decision system should have. It then turned out to be
the only reason the failure was survivable rather than silent. The transferable claim is
not "we foresaw the problem." It is: *the discipline that lets you find out your model is
wrong only exists if you adopted it while you still thought it was right.*

**The most dangerous number in machine learning is the one that makes you happy.** A PR-AUC
of 0.9983 on a 0.13%-prevalence problem should trigger an investigation, not a
celebration. Treat a too-good result as a hypothesis to be falsified.

**Fixing the leak is not the end of the investigation — it is the beginning of the real
one.** We removed the artifacts and the leak went to exactly zero. If we had stopped there,
we would have declared victory on the remediation and shipped a model with no behavioural
signal in it. The gate's third strand — *is there anything left?* — is the one that told us
the truth, and it is the one most likely to be omitted from a leakage check that only asks
"did we remove the leak?"

**A gate that flexes is not a gate.** 0.3369 fails against 0.50 and passes against 0.30,
and the threshold lives in a YAML file. Every argument in this document depends on that
number not having moved.

**Separate the product from the model.** The model was one input behind an interface, so
excluding it was an operating state rather than a crisis. Any layer that can be removed
without cascading is a layer whose failure you can survive.

**Trustworthy AI is a systems property, not a model property.** The trustworthy thing about
this system is not the model — the model is ineligible and excluded. It is the
architecture: layer separation, deterministic grounding, mandatory human disposition,
append-only audit, reconstructability. That is the transferable contribution, and it
survived the failure of the component everyone assumes is the point.

**Evaluate datasets empirically, not documentarily.** PaySim would have scored well on any
comparison matrix. Its two fatal properties surfaced only when it was trained on and
interrogated. A dataset is not a set of columns; it is a data-generating process, and you
cannot read a data-generating process off a schema.

---

## 11. What Version 2 is intended to improve

V1's limitations are specific, and V2 is scoped to them rather than to a wish list.

**Priority 1 — the dataset, then the model.** This is the whole game. The leakage
investigation produced an unambiguous, evidence-backed indictment of PaySim: the leak was
fully removed and there was almost no behavioural signal underneath it. So V2 replaces the
modelling dataset with one that can genuinely support behavioural fraud detection, and only
then rebuilds the scorer.

The selection criterion is the lesson of §9, made procedural: **no dataset is selected on
paper.** V1's leakage gate is repurposed from a model check into a *dataset selection
tool*. Candidates must pass an **account-recurrence check** (does per-account history
actually exist?) and the **leakage gate** (permutation importance + ablation) before being
adopted — not after. The gate is the most valuable asset V1 produced, and it is worth more
pointed at data than at models.

If no candidate dataset passes, that is itself a finding, and the honest response is another
documented exclusion — not a softened gate.

**Priority 2 — restore the intended operational mode.** With a gate-passing, calibrated
scorer, the dormant present-score path in the recommendation policy activates, and the
system can finally recommend **`clear`** — which V1 structurally could not do. That is the
single most visible product change in V2, and it is the direct payoff of the architecture
V1 built and never got to exercise.

The honest-degradation path stays. The templated explainer, the transparent no-score state,
rules-only operation — none of it is removed. It becomes the *fallback* rather than the
default. The day a future model fails a gate, the product should survive it exactly as V1
did.

**Priorities 3 and 4** — analyst productivity (search, pagination, notes, better evidence
visualisation, LLM explanation quality with a *measured* grounding rate) and production
hardening (auth, database-level append-only enforcement, monitoring, security review) — are
real, but they improve a product that already works. They are secondary to making the
product work as it was designed to.

**The two rules that carry over:**

1. **The leakage gate does not flex.** It now governs dataset selection *and* model
   eligibility. A model — or a dataset — that fails is excluded and the failure is
   documented.
2. **The model is not the product.** Even when V2's scorer passes and goes operational, the
   architecture must still run without it.

---

*All quantitative results in this document were measured on synthetic PaySim data and are
sourced from the committed artifacts under `evaluation/reports/`. The Version 1
machine-learning scorer is ineligible under the simulator-leakage gate and is excluded from
the operational path. No claim of real-world fraud-detection performance is made.*


Despite excluding the machine learning scorer, Version 1 successfully delivered:

• Analyst workspace
• Rule engine
• Evidence assembly
• Recommendation policy
• Grounded explanations
• Human review
• Audit trail
• Decision reconstructability
• Reproducible evaluation
• Cloud deployment

The exclusion of the scorer therefore represented a reduction in capability rather than failure of the product.