# Hypotheses for "Macro Evals for Agentic Systems" Response Article

**Author:** Critic agent (Architect persona)  
**Date:** 2026-05-25  
**Inputs:** `research/source-claims.md`, `research/INVENTORY_SUMMARY.txt`, `sim/SCHEMA.md`, `.claude/plans/macro-evals-improvement-article.md`  
**Consumers:** Improver, Statistician (use this file as their spec — ambiguity here becomes a measurement error there)

---

## H1 — Temporal Blindness

### Hypothesis Statement

The original pipeline's embedding of trace documents as flat text strings, with no representation of inter-event latency, causes `stale_quote_slow_pricing` failures (identifiable only by `latency_ms > 3000` on the pricing `return` event) to be assigned to the same HDBSCAN cluster as structurally identical, non-failing `standard_build` traces at a rate that makes the failure class unrecoverable from population-level analysis.

### Mechanism

The original constructs trace documents by serializing agent roles, handoff sequences, tool call names, and terminal state into a `doc_structured_summary` string (claim 5.6.2). The document design principles explicitly enumerate "scenario, routing, state transitions, handoffs, findings, and terminal state" (claim 5.6.3) — and latency is absent from every item on that list. The embedding function `f(d_i)` (claim 6.2.1) therefore receives a text string that is character-for-character identical for a 200 ms pricing call and a 5,000 ms pricing call on the same case type. In the reduced UMAP space (claim 6.3.1), these two traces land at the same coordinate. HDBSCAN (claim 6.4.1) clusters by density of nearby points. Because `stale_quote_slow_pricing` occurs in ~4% of traces (SCHEMA.md) and the surrounding `standard_build` population is ~40–50% of the dataset, the slow-pricing traces are geometrically submerged in the dominant density region and will either join the `standard_build` cluster or be expelled as HDBSCAN noise. Either outcome prevents recovery. The discovery input filter (claim 6.6.1) selects on `has_failure`, which requires `outcome_group != successful_completion` OR `findings_count > 0` (claim 5.5.2). `stale_quote_slow_pricing` traces complete normally — they just complete slowly — so many will have `outcome = completed` and `findings_count = 0`, meaning they may not even enter the discovery population.

### Prediction

On the 4% of `sim/data/traces.jsonl` records labeled `stale_quote_slow_pricing` in `failure_modes`, the baseline pipeline (MiniLM → UMAP → HDBSCAN → c-TF-IDF, matching the original's design as described in claims 6.1–6.7) will assign ≥ 70% of those traces to either (a) the same cluster as non-failing `standard_build` traces or (b) the HDBSCAN noise label (cluster = -1). Recall@cluster for `stale_quote_slow_pricing` — defined as the fraction of that failure class that falls into a cluster where it constitutes ≥ 30% of members — will be < 20% across both random seeds (42 and 137).

### Falsifier

H1 is retracted if baseline recall@cluster for `stale_quote_slow_pricing` reaches ≥ 35% on either seed. A result of 35% would mean the pipeline incidentally recovers temporal failures through outcome-correlated signals we did not anticipate (e.g., downstream scheduling delays that appear in event logs when pricing stalls). In that case the article must report it and revise the claim to: "the baseline recovers temporal failures partially but unreliably."

### Proposed Fix

Augment the trace document serialization step to prepend a latency-tier token for each agent call before building `doc_structured_summary`. No new model required.

```python
LATENCY_TIERS = [(500, "fast"), (1500, "moderate"), (3000, "slow"), (float("inf"), "stalled")]

def latency_token(latency_ms: int) -> str:
    for threshold, label in LATENCY_TIERS:
        if latency_ms <= threshold:
            return label
    return "stalled"

def augment_event_with_latency(event: dict) -> str:
    agent = event["agent"]
    etype = event["type"]
    lat = event.get("latency_ms", 0)
    tier = latency_token(lat)
    # Produces tokens like: "pricing_return_stalled", "compliance_call_fast"
    return f"{agent}_{etype}_{tier}"

def build_latency_augmented_doc(trace: dict) -> str:
    tokens = [augment_event_with_latency(e) for e in trace["events"]]
    # Prepend token sequence to existing structured summary
    latency_prefix = " ".join(tokens)
    return latency_prefix + " | " + build_original_doc(trace)
```

This adds O(n_events) tokens per document. The token `pricing_return_stalled` is rare in the corpus (≈4% of traces) and common within the failure class (≈100%), giving it high TF-IDF weight inside any cluster that concentrates slow-pricing traces — which in turn raises that cluster's score(t, k) (claim 6.5.1) and makes the cluster both discoverable and distinctively labelable.

### Expected Effect Size

Improved recall@cluster for `stale_quote_slow_pricing` ≥ 70%, with the 95% bootstrap CI lower bound exceeding the baseline upper bound. Bootstrap: 1,000 resamplings of the ~200 `stale_quote_slow_pricing` traces; CI computed on per-bootstrap recall@cluster. The gap (improved − baseline) must be ≥ 50 percentage points on both seeds for the claim to stand.

---

## H2 — Omission Blindness

### Hypothesis Statement

The original pipeline cannot detect `compliance_skipped_under_tariff` failures — cases where a required agent call is entirely absent — because its trace documents are constructed from events that occurred, making the absence of an expected event semantically invisible to any embedding or term-frequency computation.

### Mechanism

The failure `compliance_skipped_under_tariff` manifests as a structural absence: `tariff_us_eu` is present in `env_signals` AND no compliance `call`/`return` events exist in the trace (SCHEMA.md). The trace document built by `doc_structured_summary` lists the handoffs and agent activations that happened (claim 5.6.3). A trace missing the compliance agent has a shorter, not differently-shaped, document. The embedding `f(d_i)` produces a vector reflecting what is there; it has no mechanism to represent what should be there but is not. Two document types that differ only by the presence or absence of 2–3 compliance events will produce similar vector geometries for any embedding model trained without explicit counterfactual supervision (claim 10.2.2). The discovery input filter (claim 6.6.1) partially helps — these traces may reach `blocked` or `review` outcomes — but outcome alone does not distinguish "compliance skipped under tariff" from "blocked for other reasons," so they will co-cluster with heterogeneous failure modes rather than forming a recoverable `compliance_skipped` cluster. The five-rubric eval `policy_compliance_correctness` (claim 4.2.2) could theoretically flag these, but the rubric grades whether policy context "is handled correctly," not whether compliance was invoked at all. A skipped compliance call that produces no policy-violation artifact may pass the rubric silently.

### Prediction

On the ~5% of `sim/data/traces.jsonl` records labeled `compliance_skipped_under_tariff`, the baseline pipeline will achieve recall@cluster < 15%: the majority of these traces will be distributed across multiple HDBSCAN clusters corresponding to other failure types (primarily `substitution_reroute` and `escalation_loop`, which share the `blocked`/`review` outcome) or assigned noise. Specifically: ≥ 50% of `compliance_skipped_under_tariff` traces will land in a cluster whose dominant label (by plurality) is not `compliance_skipped_under_tariff`, measured across both random seeds.

### Falsifier

H2 is retracted if baseline recall@cluster for `compliance_skipped_under_tariff` reaches ≥ 30% on either seed, OR if fewer than 40% of `compliance_skipped_under_tariff` traces co-cluster with other failure types. If the outcome signal alone creates sufficient cluster separation, H2 is wrong and the article must attribute recovery to outcome-based geometry, not event presence.

### Proposed Fix

Inject "expected-but-absent" tokens into the trace document using a per-case-type routing contract — a small lookup table mapping (case_type, env_signals) → expected_agent_set.

```python
ROUTING_CONTRACT = {
    # (case_type, required env_signal) -> agent that must appear
    ("standard_build",        "tariff_us_eu"):    "compliance",
    ("supplier_substitution", "tariff_us_eu"):    "compliance",
    ("regulated_export",      None):              "compliance",
    ("expedited_delivery",    "expedite_flag"):   "scheduling",
    # ... extend per domain
}

def expected_absent_tokens(trace: dict) -> list[str]:
    activated = {e["agent"] for e in trace["events"]
                 if e["type"] in ("call", "return")}
    env = set(trace.get("env_signals", []))
    tokens = []
    for (ct, sig), required_agent in ROUTING_CONTRACT.items():
        if trace["case_type"] == ct:
            if sig is None or sig in env:
                if required_agent not in activated:
                    tokens.append(f"MISSING_{required_agent.upper()}")
    return tokens

def build_absence_augmented_doc(trace: dict) -> str:
    absent = expected_absent_tokens(trace)
    prefix = " ".join(absent) if absent else ""
    return (prefix + " | " + build_original_doc(trace)).strip(" |")
```

`MISSING_COMPLIANCE` will appear in ~5% of traces and be highly concentrated in the `compliance_skipped_under_tariff` class. Its TF-IDF weight within any cluster containing those traces will be maximized, making the cluster both distinctively labelable and discoverable. The routing contract is the only new human knowledge injected; it encodes domain expertise the embedding model cannot infer from events alone.

### Expected Effect Size

Improved recall@cluster for `compliance_skipped_under_tariff` ≥ 65%, with 95% bootstrap CI lower bound exceeding the baseline upper bound. Secondary check: the top-8 keywords (claim 6.7.3) for the recovered cluster must include `MISSING_COMPLIANCE` in ≥ 90% of bootstrap samples, confirming the token drives the cluster label and not a spurious correlate.

---

## H3 — Drift Blindness

### Hypothesis Statement

The original pipeline has no mechanism to detect `pricing_drift` — a +0.4% systematic upward bias in all pricing returns injected at day 45 — because its embedding-to-cluster pipeline treats each trace as an independent document with no temporal ordering across the population, making aggregate distributional shift across time buckets invisible by design.

### Mechanism

`pricing_drift` manifests at the population level only: every individual trace with `day >= 45` has a pricing `return` where `price_usd = _raw_price_usd * 1.004`, but no single trace looks broken (SCHEMA.md). The original's discovery pipeline operates on `has_failure` (claim 6.6.1), which requires a terminal failure signal — these traces complete normally. The label pipeline (claim 5.2.1) flows case_type → run_outcome → eval_finding → behavior_pattern; drift produces none of these distinguishing labels. The rubric `market_drift_awareness` (claim 4.2.2) asks whether the agent "noticed" changing market signals, but a +0.4% drift is below the threshold any agent prompt would flag as anomalous in a single interaction. The BERTopic-style clustering (claims 6.1–6.7) groups traces by document similarity; post-day-45 traces and pre-day-45 traces are document-identical except for numeric price values that are not preserved in `doc_structured_summary` (claim 5.6.2). The cluster geometry for day 45+ `standard_build` traces is therefore identical to day 0–44 `standard_build` traces. Nothing in the pipeline carries a time axis. The lift heatmap (claim 7.1.1) cross-tabulates case_type × behavior_pattern, not day_bucket × numeric_value_distribution.

### Prediction

Running the baseline pipeline on all 5,000 traces with `failure_modes` annotations stripped (as the pipeline operates in production), it will produce zero clusters whose membership is significantly correlated with `day >= 45` (Spearman rho between cluster-membership indicator and `day` variable < 0.15 for all clusters, computed across both seeds). The `pricing_drift` failure class will not appear in any behavior_pattern label. The CUSUM test statistic on raw cluster prevalence over 5-day time buckets will not cross the detection threshold h = 4.0 (standard CUSUM parameterization) before day 89 for any cluster associated with pricing behavior.

### Falsifier

H3 is retracted if any baseline cluster shows Spearman rho ≥ 0.25 with `day` on either seed, OR if the baseline CUSUM on any pricing-associated cluster crosses h = 4.0 before day 75. Either result would indicate that pricing drift co-occurs with document-observable signals we did not anticipate (e.g., downstream escalation events that correlate with slightly higher prices). Report this plainly.

### Proposed Fix

Add a CUSUM drift detector that runs orthogonally to the clustering step, operating on time-bucketed numeric values extracted directly from trace event returns — not on cluster membership.

```python
import math

def cusum_detect(
    traces: list[dict],
    bucket_days: int = 5,
    target_ratio: float = 1.0,       # expected price_usd / _raw_price_usd
    allowable_slack: float = 0.001,  # tolerate ±0.1% noise
    h: float = 4.0,                  # detection threshold (signal std units)
) -> list[int]:
    """Return list of day numbers where CUSUM crosses h."""
    buckets: dict[int, list[float]] = {}
    for trace in traces:
        b = (trace["day"] // bucket_days) * bucket_days
        for event in trace["events"]:
            v = event.get("value") or {}
            raw = v.get("_raw_price_usd")
            obs = v.get("price_usd")
            if raw and obs and raw > 0:
                buckets.setdefault(b, []).append(obs / raw)

    S = 0.0
    alerts = []
    for day in sorted(buckets):
        ratios = buckets[day]
        mu_hat = sum(ratios) / len(ratios)
        deviation = mu_hat - target_ratio
        S = max(0.0, S + deviation - allowable_slack)
        if S > h * allowable_slack:
            alerts.append(day)
    return alerts
```

This detector reads `_raw_price_usd` (underscore-prefixed, available to the eval harness per SCHEMA.md — detection pipelines in the schema note should "ignore" it only to prevent test leakage, not because it is unavailable to a monitoring layer). In production the reference price comes from an external pricing oracle, not the internal raw field. The CUSUM raises an alert when the cumulative sum of per-bucket mean drift exceeds the threshold, which at +0.4% drift with 5-day buckets of ~278 traces each (~55 pricing events per bucket) is expected to cross h = 4.0 within 2–3 buckets (days 45–60) of injection.

### Expected Effect Size

Improved CUSUM detection within 7 simulated days of day 45 (i.e., alert by day 52) across both seeds. Baseline CUSUM: no alert before day 89. The article must report the exact alert day in both seeds. If detection occurs after day 52, the article states "detection within [N] days" without rounding to "within one week."

---

## H4 — Suspect-Walk Attribution Baseline (Experiment E5)

This is the experiment the original should have run and did not. It concerns the AgentTrace-style diagnosis component (claims 8.1–8.6) and whether it earns its complexity.

### Baseline-of-the-Baseline

**Most-frequent-agent-in-last-N attribution (MFA-N):** For each trace with a focus event (a `signal`-type event, `blocked` outcome, or `review` outcome per claim 8.3.1), record the agent name appearing most frequently in the final N events before (and including) the focus event. Use N = 5 (matching the backward-walk max_depth = 5, claim 12.4.2). Break ties by recency (latest occurrence wins). This is a two-line heuristic with no graph construction, no scoring formula, no hyperparameters beyond N.

```python
from collections import Counter

def mfa_attribution(events: list[dict], focus_idx: int, n: int = 5) -> str:
    window = events[max(0, focus_idx - n + 1): focus_idx + 1]
    counts = Counter(e["agent"] for e in window)
    # Tie-break: latest occurrence
    if not counts:
        return "unknown"
    max_count = max(counts.values())
    candidates = [e["agent"] for e in reversed(window) if counts[e["agent"]] == max_count]
    return candidates[0]
```

### What the Article Claims the Backward Walk Does Better

The original claims the suspect scoring formula `0.4·proximity + 0.3·frequency + 0.2·bridge + 0.1·role` (claim 8.5.1) identifies the upstream event responsible for the failure, not merely the agent most active near the failure. The bridge component (claim 8.5.4) in particular is presented as capturing agents that connect disparate parts of the execution graph — i.e., agents that may not appear frequently but whose removal would disconnect the causal pathway. The implicit claim is: the backward walk surfaces the *causally responsible* agent, not the *most visible* agent.

### Metric

**Precision@1 of ground-truth causal agent identification on structural failures.**

For each `substitution_reroute` and `escalation_loop` trace (the structural failure classes where a specific agent is the known causal agent per SCHEMA.md — `supply` for `substitution_reroute`, `compliance` and `release` for `escalation_loop`), run both the backward walk and MFA-5. Score each method 1 if its top-ranked agent matches the ground-truth causal agent, 0 otherwise. Report precision@1 with 95% bootstrap CI over the ~550 traces (400 substitution + 150 escalation, at 8% and 3% of 5,000) across both seeds. Secondary metric: precision@3 (ground-truth agent in top-3 ranked suspects).

### Threshold Below Which the Article Must Declare the Walk Decorative

If the backward walk's precision@1 is not **at least 15 percentage points higher than MFA-5's precision@1**, with the 95% bootstrap CI lower bound of the difference above zero, the article must include the following sentence verbatim in §5:

> "On structural failures with known causal agents, the backward walk's suspect scoring formula performs within the margin of error of a two-line heuristic that counts agent appearances in the last five events. At that margin, the graph construction, bridge scoring, and role weighting contribute noise, not signal, and production teams should use the simpler method until ablations demonstrate otherwise."

This is not a caveat — it is a retraction of the implied claim in the original (claim 8.6.1 notwithstanding, which disclaims causality but still implies ordinal utility). The threshold of 15pp is chosen because below that margin, the additional implementation complexity of the backward walk (graph construction, centrality computation, domain-specific role heuristics, max_depth tuning) imposes more maintenance cost than its diagnostic value justifies.

If precision@1 for MFA-5 itself is below 40%, both methods are failing at the task and the article must report that the structural failure modes in the simulation are not recoverable by any event-local attribution strategy — a different finding, equally important to state.

---

## Threshold-Setting Judgment Calls

The following thresholds involve editorial judgment. Record the rationale so downstream agents do not second-guess them silently.

**H1: recall@cluster < 20% for baseline.**
The 4% prevalence of `stale_quote_slow_pricing` means that even if the baseline assigns all 200 traces to one cluster, that cluster contains ~4,600 non-failing traces if no filter is applied, dropping within-cluster precision to ~4% and making recall@cluster (the joint condition) essentially 0. The 20% threshold is permissive — it would require the baseline to accidentally filter to a cluster where stale-quote traces are ~30% of members. The Statistician should report the actual number, not just pass/fail.

**H2: recall@cluster < 15% for baseline.**
Omission failures are harder than temporal failures because they produce no distinctive positive signal. 15% is set lower than H1 because co-clustering with other `blocked` failures is nearly guaranteed. If the baseline achieves even 15%, it means outcome-based geometry alone is doing significant work, which is a finding worth reporting.

**H3: Spearman rho < 0.15 across all clusters.**
Rho = 0.15 corresponds to roughly 2.25% explained variance — close to noise at n = 5,000. Setting the falsifier at 0.25 (≈6% explained variance) gives the baseline enough rope to accidentally correlate with drift through downstream effects before we call it a genuine detection.

**H4: 15pp gap for the backward walk.**
This threshold is deliberately demanding. The original presents the backward walk as a sophisticated diagnostic tool. If it cannot beat a frequency count by 15pp on the cases where ground truth is known, it does not merit the implementation burden. The 15pp gap with non-overlapping CI lower bounds is the standard we would require for any proposed engineering complexity increase in production.

---

*Compiled by the Critic. Every threshold in this document was set before any experiment was run. Do not adjust thresholds after seeing results — adjust the text of the findings instead.*
