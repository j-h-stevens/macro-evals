# Pre-Registration — Experiments E1–E6

**Author:** Statistician
**Date:** 2026-05-25
**Status:** WRITTEN BEFORE ANY RESULT COMPUTATION
**Inputs spec:** `research/hypotheses.md` (H1–H4), `sim/SCHEMA.md`
**Random seed:** 42 for all sampling/bootstrap
**Bootstrap config:** `n_resamples = 1000`, **percentile** CIs, **95%** level
  (BCa was considered; we use percentile because several of our statistics are bounded ratios on small subgroups (~150–250 traces) where BCa's acceleration term is noisy. Percentile CIs are reported throughout for consistency.)

A note on seeds: `hypotheses.md` predicts behavior "across both seeds 42 and 137." The available pipeline outputs (`baseline/outputs/`, `improved/outputs/`) were produced under seed 42 only. We do not re-run the pipelines. All verdicts in this study are therefore evaluated on **seed 42 only**, and we explicitly mark the "across seeds" portion of each hypothesis as out-of-scope for this artifact.

---

## Universal Definitions

### "Majority cluster" for a failure mode F

The HDBSCAN cluster containing the **plurality of F-labeled traces**, computed over assigned clusters only — i.e., `cluster_id != -1` (noise) is excluded from the search for the majority cluster. Tie-break (two clusters tied for plurality): smaller `cluster_id` wins. (Deterministic; no result in our actual data ties.)

### "Recall@cluster" for failure mode F

`recall@cluster(F) = (# traces with F whose assigned cluster_id == majority_cluster(F)) / (total # traces with F)`

The majority cluster is *not* required to be label-dominated by F; it is simply the cluster that holds the most F-traces. This is the most permissive reading of "the pipeline recovers this failure mode." A stricter reading (require ≥30% within-cluster purity for F) is reported as a **secondary** number per hypothesis text for H1, but the **primary verdict** uses the recall@cluster definition above.

Noise cluster (`-1`) is excluded from being the majority cluster. If excluding noise yields no F-traces in any positive cluster, recall@cluster = 0.

### Bootstrap procedure

For a per-trace statistic computed on a subgroup of size n (e.g., the n traces with failure mode F):

1. Resample the n traces with replacement, 1000 times, seeded with `numpy.random.default_rng(42)`.
2. Recompute the statistic on each resample, **holding the cluster assignment fixed** (i.e., the majority cluster is computed once on the full data; bootstrap only resamples the per-trace indicator of "in majority cluster"). This is appropriate because pipeline clusters are not re-fit in production each query.
3. Report the 2.5th and 97.5th percentiles as the 95% CI.

For **paired gap** statistics (improved − baseline on the same set of F-labeled traces): resample trace indices; compute baseline and improved indicators on the same resampled indices; take the difference. CI on the gap is the percentile CI of those 1000 paired differences.

---

## Experiment Definitions

### E1 — Baseline recall on structural failures (sanity)

- **Question:** Does the baseline pipeline recover the structural failures (`substitution_reroute`, `escalation_loop`) it is supposed to handle well?
- **Slice:** all traces with `substitution_reroute` in `failure_modes`; separately, all with `escalation_loop`.
- **Metric:** `recall@cluster` for each, on **baseline** outputs.
- **Threshold (pre-registered):** SUPPORTS the "baseline works on structural" sanity check if recall@cluster ≥ 0.50 for `substitution_reroute` AND ≥ 0.50 for `escalation_loop`. REFUTES otherwise.
- **Bootstrap:** percentile, 1000 resamples, on the subgroup.

### E2 — Temporal blindness (H1)

- **Question:** Does the improved pipeline recover `stale_quote_slow_pricing` materially better than baseline?
- **Slice:** all traces with `stale_quote_slow_pricing` in `failure_modes`.
- **Metrics:**
  - Primary: paired gap = `recall@cluster_improved − recall@cluster_baseline`.
  - Secondary (H1 verbatim): is baseline recall@cluster < 0.20 and improved ≥ 0.70?
- **Threshold for SUPPORTS (H1, primary):** the CI lower bound on the gap exceeds **+0.50** (i.e., ≥ 50pp gap as required by hypothesis "Expected Effect Size").
- **Threshold for REFUTES (H1, falsifier):** baseline recall@cluster ≥ 0.35 OR the gap CI lower bound is ≤ 0.
- **Bootstrap:** percentile, paired, 1000 resamples.

### E3 — Omission blindness (H2)

- **Question:** Does the improved pipeline recover `compliance_skipped_under_tariff` materially better than baseline?
- **Slice:** all traces with `compliance_skipped_under_tariff` in `failure_modes`.
- **Metrics:** paired gap as in E2.
- **Threshold for SUPPORTS:** gap CI lower bound > 0 AND improved recall@cluster ≥ 0.65 (per H2 expected effect size) AND baseline recall@cluster < 0.30 (the falsifier in H2).
- **Threshold for REFUTES:** baseline recall@cluster ≥ 0.30, OR gap CI lower bound ≤ 0.
- **Bootstrap:** percentile, paired, 1000 resamples.

### E4 — Drift detection (H3)

- **Question:** What is the time-to-detection (days from injection at day 45) for `pricing_drift` under baseline vs improved?
- **Slice:** the whole 5000-trace dataset; ground-truth injection day = 45.
- **Metrics:**
  - Baseline: no detector exists in `baseline/outputs/` (no `drift_alerts.csv`). Reported as `inf` ("no mechanism"). No bootstrap.
  - Improved: from `improved/outputs/drift_alerts.csv`, the **minimum** `alert_day` across all rows, and the case-type stratum that alerted first.
- **Threshold for SUPPORTS:** improved alert_day ≤ 52 (per H3 expected effect size = within 7 days of injection).
- **Threshold for REFUTES:** improved earliest alert_day > 75 (per H3 falsifier).
- **Intermediate (52 < day ≤ 75):** SUPPORTS but with explicit "detected within N days, not within one week."

### E5 — Suspect-walk attribution (H4)

- **Question:** Does the cookbook backward-walk's precision@1 beat the MFA-5 baseline by ≥ 15pp on structural-failure clusters?
- **Slice:** traces with `substitution_reroute` or `escalation_loop` in `failure_modes`. (These are the failure classes with a known ground-truth causal agent.)
- **Ground-truth causal-agent mapping (pre-registered):**
  - `substitution_reroute` → `supply`
  - `escalation_loop` → `compliance` (acceptable alternates: also score 1 if top-1 = `release`, because SCHEMA.md notes both compliance and release participate; we report **two** numbers: strict (`compliance` only) and lenient (`compliance` OR `release`). Strict is the primary metric.)
  - `stale_quote_slow_pricing` → `pricing` (NOT used in E5 primary; pricing is not "structural" per H4 spec, but reported as secondary)
  - `compliance_skipped_under_tariff` → `compliance` (NOT used in E5; absence cannot be attributed to an agent that did not appear)
  - `pricing_drift` → no per-trace agent; excluded from E5 per H4 spec.
- **MFA-5 baseline:** for each trace in the slice, identify the focus event as the **first** `signal`-type event, or if none, the last event whose immediate context produces `outcome ∈ {blocked, review}`, or if outcome is `completed/failed` and no signal exists, the last event in the trace. Window = last 5 events including focus. Most frequent agent; ties broken by **latest occurrence**.
- **Backward-walk top-1:** from `suspects.csv`, per cluster, the agent with the maximum `suspect_score`. Each trace in the slice is mapped to its assigned cluster's top-1 suspect. Traces whose cluster has no suspects-csv entry (or are in noise cluster -1 with no suspects) are scored 0.
- **Metric:** precision@1 = mean indicator over the slice.
- **Primary verdict (cookbook claim):** backward walk's precision@1 minus MFA-5's precision@1.
  - SUPPORTS the cookbook's implicit claim: gap ≥ +0.15 AND CI lower bound > 0.
  - REFUTES: gap < +0.15, OR CI lower bound ≤ 0. In this case the article must include the verbatim sentence from H4.
- **Secondary:** if MFA-5 precision@1 < 0.40, report that "structural failures are not recoverable by event-local attribution" per H4 spec.
- **Bootstrap:** percentile, paired on trace indices, 1000 resamples.

### E6 — Adversarial check

- **Question:** Does the improved pipeline regress on any failure mode relative to baseline?
- **Slice:** each of the 6 failure modes (`substitution_reroute`, `compliance_skipped_under_tariff`, `stale_quote_slow_pricing`, `pricing_drift`, `escalation_loop`, `random_noise_failure`).
- **Metric:** per-mode `recall@cluster_improved − recall@cluster_baseline`, with 95% CI on the gap.
- **Threshold for REGRESSION:** gap CI upper bound < 0 (i.e., the entire CI is below zero — improved is convincingly worse).
- **Soft regression flag:** point estimate negative but CI crosses zero — reported but not declared regression.
- **Bootstrap:** percentile, paired, 1000 resamples per mode.

---

## What we will NOT do

- No re-tuning of metric definitions after seeing point estimates. The definitions above are final.
- No "drop the noise cluster post-hoc" — `cluster_id = -1` is already excluded from the *majority cluster search* per the universal definition above. It is NOT excluded from the denominator of recall@cluster: a trace in the noise cluster counts against recall.
- No slice cherry-picking (e.g., "recall@cluster on traces where the trace also has outcome=blocked" — out of scope).
- No swapping percentile→BCa or 95%→90% post-hoc.
- No replacing "majority cluster" with "best cluster across all clusters that hold ≥k F-traces" — that would let us pick the most flattering cluster.
- No averaging over seeds — seed 137 outputs do not exist in the supplied artifacts; we report seed-42 only and disclose this in `results.md`.
- No softening of inconvenient verdicts. If H1/H2/H3/H4 fail their pre-registered thresholds, results.md says REFUTES.
- No editing of pipeline code; we consume their outputs only.
- No reading of underscore-prefixed fields by the baseline/improved pipelines (the drift detector in `improved/` already alerts; we do not re-run it).

---

## Output files

- `eval/metrics.py` — re-runnable implementation
- `eval/results.md` — verdicts
- `eval/raw_numbers.json` — machine-readable estimates and CIs

Seed = 42, n_resamples = 1000, CI = 95% percentile, throughout.
