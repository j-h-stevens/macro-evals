# Seed sweep results (E1, E2, E3, E5)

Seeds run: [7, 42, 137, 2024, 31337].  E4 omitted: CUSUM drift detector is deterministic and cluster-independent; seed has no effect on it.

Per-seed artifacts in `eval/seed_sweep_outputs/seed_<S>/`. Raw rows in `eval/seed_sweep_raw.jsonl`. The train/test partition is salted by seed (`hash((trace_id, seed)) % 5 == 0` -> held-out), so even the 20% held-out *set* changes between seeds, not just the cluster fit.

## E1 — baseline structural recall

Per-seed recall@cluster for substitution_reroute and escalation_loop (baseline pipeline, full dataset). Verdict = SUPPORTS iff both >= 0.50.

| Metric | Seed 7 | Seed 42 | Seed 137 | Seed 2024 | Seed 31337 | Range | Verdict-stability |
|---|---|---|---|---|---|---|---|
| substitution recall | 0.167 | 0.222 | 0.116 | 0.222 | 0.116 | [0.116, 0.222] | — |
| escalation recall | 0.699 | 0.252 | 0.301 | 0.252 | 0.217 | [0.217, 0.699] | — |
| **E1 verdict** | REFUTES | REFUTES | REFUTES | REFUTES | REFUTES | — | **ROBUST** |

## E2 — H1 temporal (stale_quote_slow_pricing)

In-sample gap = improved − baseline recall@cluster on full dataset. Held-out gap = improved − baseline on the 20% test partition fit on the 80% train. Verdict thresholds: MAGNITUDE SUPPORTED (gap CI_lo > 0.50, baseline < 0.20, improved >= 0.70); DIRECTION CONFIRMED (positive gap, not refuted); REFUTED otherwise.

| Metric | Seed 7 | Seed 42 | Seed 137 | Seed 2024 | Seed 31337 | Range | Verdict-stability |
|---|---|---|---|---|---|---|---|
| in-sample gap | +0.056 | +0.082 | +0.056 | +0.041 | +0.010 | [+0.010, +0.082] | — |
| in-sample verdict | DIRECTION CONFIRMED | DIRECTION CONFIRMED | REFUTED | REFUTED | REFUTED | — | **REVERSED** |
| held-out gap | +0.000 | +0.059 | +0.000 | +0.000 | +0.000 | [+0.000, +0.059] | — |
| held-out verdict | REFUTED | REFUTED | REFUTED | REFUTED | REFUTED | — | **ROBUST** |

## E3 — H2 omission (compliance_skipped_under_tariff)

| Metric | Seed 7 | Seed 42 | Seed 137 | Seed 2024 | Seed 31337 | Range | Verdict-stability |
|---|---|---|---|---|---|---|---|
| in-sample gap | +0.036 | -0.004 | -0.004 | -0.004 | -0.077 | [-0.077, +0.036] | — |
| in-sample verdict | REFUTED | REFUTED | REFUTED | REFUTED | REFUTED | — | **ROBUST** |

## E5 — backward walk vs MFA-5 (the headline finding)

Gap = backward_walk_precision@1 − MFA-5_precision@1 over structural traces (substitution_reroute + escalation_loop). Lenient ground truth is the load-bearing one (escalation_loop GT = {compliance, release}).

| Metric | Seed 7 | Seed 42 | Seed 137 | Seed 2024 | Seed 31337 | Range | Verdict-stability |
|---|---|---|---|---|---|---|---|
| in-sample lenient gap | +0.000 | -0.060 | -0.038 | -0.060 | -0.069 | [-0.069, +0.000] | — |
| in-sample lenient verdict | NULL | MFA-5 BEATS WALK | MFA-5 BEATS WALK | MFA-5 BEATS WALK | MFA-5 BEATS WALK | — | **MIXED** |
| in-sample strict gap | -0.004 | -0.004 | -0.004 | -0.004 | -0.004 | [-0.004, -0.004] | — |
| in-sample strict verdict | NULL | NULL | NULL | NULL | NULL | — | **ROBUST** |

## Interpretation

**E5 lenient verdict is MIXED across seeds, but the direction is one-sided.** Four of five seeds (42, 137, 2024, 31337) give "MFA-5 BEATS WALK"; seed 7 collapses to NULL with a point gap of exactly 0.000. No seed reverses the sign in favor of the walk. The headline qualitative claim — "the backward walk does not beat MFA-5 on this workload" — survives in all five seeds; the stronger claim "the walk *loses* to MFA-5" survives in four. The article should report the headline as **robust in direction, mixed in significance**, not as a single-seed artifact.

**E5 strict verdict is ROBUST across all five seeds (all NULL):** strict precision@1 is at the floor (0.0–0.004) for both methods, an unrecoverable structural failure rate for either MFA-5 or the backward walk at this depth. This is the floor-effect the article already discusses; it replicates everywhere.

**E2 held-out reversal is ROBUST: every seed refutes E2 on held-out.** Four of five seeds collapse to gap=0.000 because the train-fit majority cluster coincides between baseline and improved (the dustbin-cluster pattern from §"The 'wins' we did see are mostly one cluster" reasserts itself), and the one seed (42) with a positive held-out gap is still REFUTED on the verdict thresholds. The in-sample H1 effect is broadly fragile, not a single-seed quirk. Note: the partition is salted (`hash((trace_id, seed)) % 5 == 0`), so the seed-42 row here uses a *different* held-out set than the unsalted `eval/held_out.py` reported in the article body (which still shows the original −0.111 gap); both refute, just by different mechanisms.

**E2 in-sample verdict is REVERSED:** seed 7 and seed 42 give DIRECTION CONFIRMED; seeds 137, 2024, 31337 give REFUTED. The gap CI lower bound dips below zero on three of five seeds. The seed-42 "direction confirmed" verdict is therefore a minority report. The article's existing downgrade ("direction is right even if the magnitude is small, but does not survive held-out") was correct in spirit; the seed sweep tightens it to "direction is itself unstable across seeds."

**E1 and E3 are ROBUST.** E1 REFUTES the cookbook's structural-recall framing in every seed; E3 (H2 omission) is a clean null in every seed.

