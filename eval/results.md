# Results — Experiments E1–E6

**Author:** Statistician
**Date:** 2026-05-25
**Seed:** 42 (single seed; pipeline outputs for seed 137 were not provided)
**Bootstrap:** 1000 resamples, 95% percentile CIs
**Pre-registration:** `eval/preregistration.md` (frozen before any computation below)
**Raw numbers:** `eval/raw_numbers.json`

> Six verdicts up front: **E1 REFUTES · E2 REFUTES · E3 REFUTES · E4 SUPPORTS · E5 REFUTES · E6 SOFT-REGRESSION-ONLY**.
>
> The headline: the improved pipeline is materially better than baseline on every failure class with a real lift, but the *absolute* recall numbers fall far short of H1/H2's pre-registered thresholds. Drift detection works on day 0 (improved CUSUM fires the day of injection). The backward suspect walk does not earn its complexity; on structural failures with known causal agents, it never names the right agent.

---

## E1 — Baseline recall on structural failures (sanity check)

**Question.** Does the baseline catch the structural failures (`substitution_reroute`, `escalation_loop`) the article assumes it handles well?

**Pre-registered threshold.** SUPPORTS if baseline `recall@cluster ≥ 0.50` for *both* modes; REFUTES otherwise.

**Result.**

| Mode | n | Majority cluster | recall@cluster | 95% CI |
|---|---:|---:|---:|---|
| `substitution_reroute` | 406 | 4 | **0.222** | [0.182, 0.261] |
| `escalation_loop`       | 143 | 86 | **0.252** | [0.182, 0.329] |

**Verdict: REFUTES.** Neither structural mode clears the 50% bar; both fall in the low-20%s. The baseline does not work as well on structural failures as the article's framing implies. Effect size: baseline structural recall is roughly **28pp below** the pre-registered "works" threshold.

**For the Writer.** The cookbook's setup assumes a baseline that competently clusters structural failures and then fails the harder modes. Our data shows the baseline is mediocre on the easy cases too. The article should not concede "structural failures are handled fine" — it should report the 22%/25% numbers.

---

## E2 — Temporal blindness (H1)

**Question.** Is the improved pipeline materially better than baseline at recovering `stale_quote_slow_pricing`?

**Pre-registered threshold.** SUPPORTS iff gap CI lower bound > +0.50 AND baseline < 0.20 AND improved ≥ 0.70. REFUTES if baseline ≥ 0.35 OR gap CI lower bound ≤ 0.

**Result.**

| Pipeline | Majority cluster | recall@cluster | 95% CI |
|---|---:|---:|---|
| Baseline | 104 | 0.051 | [0.021, 0.082] |
| Improved | 46  | 0.133 | [0.087, 0.179] |
| **Gap (improved − baseline)** | — | **+0.082** | [+0.021, +0.138] |

**Verdict: REFUTES.** The gap is positive and its CI excludes zero (a real lift), but it is nowhere near the +0.50 H1 demanded. Improved recall is 13%, not 70%.

**Effect size.** +8.2pp lift, CI [+2.1pp, +13.8pp]. The latency-token augmentation moves the needle but does not "recover" temporal failures.

**For the Writer.** H1's *mechanism* is plausible (improved beats baseline, statistically), but H1's *magnitude prediction* is wrong. The article must report **both** numbers and avoid the "the fix recovers temporal failures" framing. A defensible claim: "augmenting documents with latency tokens roughly **doubles** recall (from ~5% to ~13%), but absolute recovery remains poor — the failure class is mostly geometrically submerged even with the fix."

---

## E3 — Omission blindness (H2)

**Question.** Is the improved pipeline materially better at recovering `compliance_skipped_under_tariff`?

**Pre-registered threshold.** SUPPORTS iff gap CI lower bound > 0 AND improved ≥ 0.65 AND baseline < 0.30. REFUTES if baseline ≥ 0.30 OR gap CI lower bound ≤ 0.

**Result.**

| Pipeline | Majority cluster | recall@cluster | 95% CI |
|---|---:|---:|---|
| Baseline | 112 | 0.194 | [0.142, 0.239] |
| Improved | 73  | 0.190 | [0.146, 0.239] |
| **Gap** | — | **−0.004** | [−0.081, +0.069] |

**Verdict: REFUTES.** The improved pipeline is statistically indistinguishable from baseline on the omission class. The `MISSING_COMPLIANCE` token, as instantiated in the supplied improved outputs, does not change cluster assignment for these traces in a way that improves recall@cluster.

**Effect size.** −0.4pp, CI crosses zero. Zero effect.

**For the Writer.** H2 is the most embarrassing result for the *improved* pipeline. The fix the Improver designed does not work — at least, not as measured by recall@cluster. The article cannot claim the absence-token approach solves omission blindness. Two honest framings: (a) "the absence-token fix did not move recall@cluster, suggesting cluster geometry is dominated by outcome and shared structure with other `blocked` cases"; (b) the article may want to investigate whether a different metric (e.g., direct keyword lift on `MISSING_COMPLIANCE` within any cluster) would tell a different story — but that would be a different metric and must be reported as such, not retrofit into H2.

---

## E4 — Drift detection (H3)

**Question.** When does each pipeline detect `pricing_drift` (injected day 45)?

**Pre-registered threshold.** SUPPORTS iff improved alert_day ≤ 52. REFUTES if > 75. Intermediate: SUPPORTS with explicit "within N days" language.

**Result.**

| Pipeline | Earliest alert day | Days from injection |
|---|---:|---:|
| Baseline | ∞ (no detector exists) | n/a |
| Improved | **day 45** (stratum `case:custom_configuration`, signal `price_usd_mean`) | **0 days** |

A second alert fires at day 60 for `case:supplier_substitution`. Both alerts trip the threshold 0.004 with cumulative deviations ~0.0501.

**Verdict: SUPPORTS.** Detection fires on the day of injection. The +0.4% drift exceeds the CUSUM slack immediately at the first 5-day bucket boundary covering day 45.

**Effect size.** Baseline has no detector; improved detects at injection. Effectively: the orthogonal CUSUM mechanism is the entire delta. Note that detection here is by *construction* — CUSUM was designed against this exact drift profile, so this experiment establishes "the orthogonal detector works as advertised," not "the improved pipeline is generally better at drift."

**For the Writer.** This is the cleanest win for the improved pipeline. The article can confidently claim "CUSUM run orthogonally to clustering detects a +0.4% drift on the day of injection, while the embedding-cluster pipeline has no mechanism." Avoid generalizing to drift detection in the abstract — the result is for this specific drift signal and this specific bucket size.

---

## E5 — Suspect-walk attribution (H4)

**Question.** On structural failures with known causal agents, does the cookbook's backward suspect walk beat the two-line MFA-5 heuristic by ≥ 15pp on precision@1?

**Pre-registered threshold.** SUPPORTS iff gap ≥ +0.15 AND gap CI lower bound > 0. Otherwise REFUTES, and the article must include the verbatim sentence from H4 §"Threshold Below Which the Article Must Declare the Walk Decorative".

**Strict ground truth (preregistration §E5):** `substitution_reroute → {supply}`, `escalation_loop → {compliance}`.

**Result (strict, n = 549 structural traces):**

| Method | precision@1 | 95% CI |
|---|---:|---|
| MFA-5 | **0.004** | [0.000, 0.009] |
| Backward walk (cookbook) | **0.000** | [0.000, 0.000] |
| **Gap (BW − MFA-5)** | **−0.004** | [−0.009, 0.000] |

**Result (lenient, escalation_loop accepts `release` OR `compliance`):**

| Method | precision@1 | 95% CI |
|---|---:|---|
| MFA-5 | **0.224** | [0.189, 0.260] |
| Backward walk | **0.164** | [0.131, 0.195] |
| **Gap (BW − MFA-5)** | **−0.060** | [−0.086, −0.035] |

**Per-mode top-1 distributions** reveal the mechanism:

- **`substitution_reroute`** (n=406): MFA-5 names `orchestrator` 358 times (88%), `scheduling` 31, `release` 17 — never `supply`. Backward walk names `orchestrator` 197, `unknown` 124, `pricing` 85 — also never `supply`. Both methods are blind to the true causal agent.
- **`escalation_loop`** (n=143): MFA-5 names `release` 121 times (85%), `compliance` only 2. Backward walk names `release` 90, `unknown` 53. In the lenient scoring (accept `release`), MFA-5 beats the backward walk because the backward walk produces "unknown" (no suspects entry, or noise cluster) for 37% of traces.

**Verdict: REFUTES.** The gap is negative under both strict and lenient scoring. Under lenient, the CI on the gap is entirely below zero — the backward walk is convincingly *worse* than the heuristic, not equivalent. The MFA-5 floor warning also applies: precision@1 = 0.004 strict means structural-failure causal attribution from event-local context is not solved by either method.

**Verbatim sentence required in §5 of the article (per H4):**

> "On structural failures with known causal agents, the backward walk's suspect scoring formula performs within the margin of error of a two-line heuristic that counts agent appearances in the last five events. At that margin, the graph construction, bridge scoring, and role weighting contribute noise, not signal, and production teams should use the simpler method until ablations demonstrate otherwise."

Our results are strictly stronger than the trigger condition: the walk is not "within the margin of error" — it is *below* MFA-5 under the lenient scoring. Production teams should use MFA-5 *or* neither; the walk's complexity is unjustified by these data.

**For the Writer.** The honest framing is two-part: (1) the backward walk does not earn its complexity, full stop; (2) but neither does MFA-5 succeed at strict ground truth — both methods predict `orchestrator` and `release` everywhere because those agents are present in nearly every event window. The article should resist the urge to frame this as "MFA-5 wins"; the correct frame is "event-local frequency-based attribution does not recover the causal agent on these failure modes, and the cookbook's added machinery does not help."

---

## E6 — Adversarial check

**Question.** Does the improved pipeline regress (CI of gap entirely < 0) on any failure mode?

**Result (paired gap = improved − baseline, recall@cluster):**

| Mode | gap | 95% CI | Verdict |
|---|---:|---|---|
| `substitution_reroute` | +0.165 | [+0.089, +0.244] | improvement |
| `compliance_skipped_under_tariff` | −0.004 | [−0.081, +0.069] | **soft regression (point negative, CI crosses 0)** |
| `stale_quote_slow_pricing` | +0.082 | [+0.021, +0.138] | improvement |
| `pricing_drift` | +0.023 | [+0.014, +0.033] | improvement |
| `escalation_loop` | +0.448 | [+0.322, +0.566] | improvement |
| `random_noise_failure` | +0.103 | [+0.048, +0.161] | improvement |

**Verdict: NO HARD REGRESSION; ONE SOFT REGRESSION (compliance_skipped_under_tariff).**

**Findings.** The vocabulary additions (latency tokens, absence tokens) did **not** harm the structural classes. `substitution_reroute` recall@cluster rose 17pp and `escalation_loop` rose 45pp — a large unexpected win for `escalation_loop`. The only mode the improved pipeline did not improve is `compliance_skipped_under_tariff`, the very mode the H2 fix targeted (see E3).

**Surprises.**
1. **`escalation_loop` improvement is the biggest single effect in the whole study (+45pp).** This is incidental to H1/H2's stated mechanisms; the latency tokens may be implicitly carrying the back-and-forth pattern of the loop. The article should call this out as an unanticipated finding, not as evidence for H1 or H2.
2. **The absence-token fix for H2 produced no measurable lift** but also did no harm. This is a "the intervention is inert as currently configured" finding, which is more useful to report than to bury.
3. **`pricing_drift` recall@cluster is ~2% for baseline and ~5% for improved** — both pipelines treat drift as a no-op at the cluster level, as predicted by H3's mechanism. The actual drift detection happens entirely via the orthogonal CUSUM (E4).
4. **Multiple improved-pipeline majority clusters are cluster 116**, the largest mixed cluster in the improved outputs. That cluster's `cluster_x_failure_mode.csv` row should be examined; this is a possible "everything got grouped together" artifact worth flagging in the article's appendix.

---

## Judgment calls (disclosed)

1. **Single seed (42).** The hypotheses are written "across seeds 42 and 137"; only seed-42 pipeline outputs were provided. All verdicts in this artifact are seed-42 only. We did not re-run the pipelines (constraint: no pipeline-code edits). The Writer should mark all numbers as seed-42 and either commission a seed-137 run or weaken the article's seed-stability claims.
2. **Majority-cluster tie-break = smaller cluster_id.** No ties occurred; this is documented but not load-bearing.
3. **Noise cluster (−1) excluded from majority-cluster *search* but *counted* in recall@cluster denominator.** A trace in cluster −1 counts against recall, but no failure mode is ever assigned its "majority cluster" = −1. This is the pre-registered behavior; we did not change it after seeing the noise-cluster row in `cluster_x_failure_mode.csv` (which holds 102 of the 2666 `pricing_drift` traces).
4. **E5 ground truth for `escalation_loop` accepts both `compliance` and `release`** as "lenient" because SCHEMA.md notes both agents participate in the loop. Strict scoring (compliance only) is the headline; lenient is a robustness check. Both yield REFUTES.
5. **Focus-event selection in MFA-5.** Used: first `signal`-type event, else last event. Did not branch on outcome; the heuristic is unaltered from preregistration despite its weak result.
6. **No metric was redefined or threshold relaxed after seeing point estimates.** This is the most important constraint and it was honored.

---

*All numbers reproducible via* `python /Users/john/macro-evals-response/eval/metrics.py`.
