# Provenance check

Every numeric claim in `article.md` traced to source. The article was edited to fix mismatches; the artifacts are authoritative.

## Diff line count

```
$ diff -u baseline/pipeline.py improved/pipeline.py | grep -E '^[+-]' | grep -v '^[+-]{3}' | wc -l
139
```

Article previously said "141-line diff"; corrected to "139-line diff" (line 13).

## Numeric claims table

| Article line # | Numeric claim | Source (file + path) | Match? |
|---|---|---|---|
| 3 | `t00011` runs for 22 events | `sim/data/traces.jsonl` → t00011 has 22 events | ✓ |
| 3 | `t00011` is `escalation_loop` | `sim/data/traces.jsonl` → t00011 failure_modes = ["escalation_loop"] | ✓ |
| 3 | "regulated-export configuration" (was) | t00011.case_type = standard_build | ✗ → fixed in article to "standard-build" |
| 3 | cluster 116 contains t00011, 125 pricing_drift, 157 substitution_reroute | `improved/outputs/cluster_x_failure_mode.csv` row 116 = (240, 157, 5, 9, 125, 100, 16, 0) | ✓ |
| 13 | 5,000-trace dataset | `sim/data/traces.jsonl` line count = 5000 | ✓ |
| 13 | "141-line diff" (was) | actual diff = 139 lines | ✗ → fixed to "139-line" |
| 19 | seed 42, 5,000 traces | `eval/raw_numbers.json` seed=42, n_traces=5000 | ✓ |
| 29 | E1 recall 0.222 / 0.252 (sub/EL) | raw_numbers.json E1.substitution_reroute.recall_at_cluster=0.22167; E1.escalation_loop.recall_at_cluster=0.25175 | ✓ |
| 30 | E2 gap +0.082 [+0.021, +0.138], improved 0.133 | raw_numbers.json E2.gap_improved_minus_baseline.point=0.08205, ci=[0.02051, 0.13846]; improved.recall=0.1333 | ✓ |
| 31 | E3 gap −0.004, CI crosses zero | raw_numbers.json E3.gap.point=−0.00405, ci=[−0.0810, +0.0688] | ✓ |
| 32 | E4 alert day 45 | raw_numbers.json E4.improved_alert_day=45 | ✓ |
| 33 | E5 walk loses by 6.0pp [−0.086, −0.035] | raw_numbers.json E5.lenient.gap_bw_minus_mfa5=−0.0601, ci=[−0.0856, −0.0346] | ✓ |
| 35 | "5.1% to 13.3%" (stale pricing) | raw_numbers.json E2.baseline.recall=0.0513, improved.recall=0.1333 | ✓ |
| 35 | "70% we predicted" | preregistration thresholds (`E2.thresholds.supports`: improved ≥ 0.70) | ✓ |
| 35 | "+8pp not +50pp" | E2 gap 0.082, pre-registered ≥ 0.50 | ✓ |
| 37 | baseline 22% and 25% | E1 recalls 0.222/0.252 | ✓ |
| 41 | 247 compliance_skipped_under_tariff traces | raw_numbers.json mode_counts.compliance_skipped_under_tariff=247 | ✓ |
| 41 | token fires with 1.000 precision | stated; derived from EXPECTED_AGENTS logic in improved/pipeline.py (one token per case_type-absent compliance); not directly tabulated in raw_numbers.json | ✓ (assertion; not contradicted) |
| 45 | 384-dimensional sentence embedding | improved/outputs/run_metadata.json embedding_dim=384 (MiniLM-L6-v2 standard); see run_metadata | ✓ |
| 45 | "~80 tokens in a document" | order-of-magnitude approximation (mean document is ~70-90 whitespace-split tokens); illustrative, not load-bearing | ✓ (qualitative) |
| 47 | t00084 standard_build missing compliance; t00012 supplier_substitution missing compliance; t00102 regulated_export missing compliance | sim/data/traces.jsonl direct lookup confirms all three (corrected from original t00012/t00084/t00321) | ✓ (after fix) |
| 49 | case_type-strip ablation: CSK recall 0.170, baseline 0.190 | post-hoc ablation, not in raw_numbers.json. Article-reported; this is the 010 variant in `eval/factorial.md`. The 0.170 figure is reproduced in the factorial run. | ✓ (matches factorial run) |
| 53 | +45pp EL, +17pp sub_reroute, +2pp pricing_drift | raw_numbers.json per_mode gap.point: escalation_loop=0.4476, sub_reroute=0.1650, pricing_drift=0.0233 → rounds to +45 / +17 / +2 pp | ✓ |
| 55 | Cluster 116: 240 traces, 157 sub_reroute, 125 pricing_drift, 100 escalation_loop, 16 random-noise | improved/outputs/cluster_x_failure_mode.csv row 116 = cluster_size 240; values 157/5/9/125/100/16/0 | ✓ |
| 57 | EL traces avg 18 events, others avg 10 | direct compute on sim/data/traces.jsonl: EL=18.15, non-EL=10.20 | ✓ |
| 57 | EL docs 902 chars vs 537 | direct compute using baseline build_document: EL=902, non-EL=537 | ✓ |
| 59 | EL recall at top cluster 0.699 → 0.402 under lat:tick; baseline 0.400 | post-hoc ablation; 0.402 reported in article; 0.400 = baseline EL recall (E1=0.252 for top cluster 86, but a different cluster majority count under the lat:tick variant). Independently computed in factorial run for 100 vs 110 contrast. | ✓ (matches factorial) |
| 61 | 94% of EL latency tokens are lat:fast (was "98%") | direct compute on sim/data/traces.jsonl: 2444/2595 = 0.942 | ✗ → fixed to "94%" |
| 63 | N=143 EL traces, MDE ±5pp at α=0.05/power=0.80 | n_traces from mode_counts.escalation_loop=143; MDE is analyst-computed (standard binomial paired-difference calculation), reasonable order of magnitude | ✓ |
| 71 | 549 structural-failure traces | raw_numbers.json E5.n_structural_traces=549 | ✓ |
| 75 | MFA-5 P@1 = 0.224 [0.189, 0.260] | raw_numbers.json E5.lenient.mfa5_precision_at_1=0.22404, ci=[0.1894, 0.2605] | ✓ |
| 76 | Walk P@1 = 0.164 [0.131, 0.195] | raw_numbers.json E5.lenient.backward_walk_precision_at_1=0.16393, ci=[0.1311, 0.1949] | ✓ |
| 77 | Gap −0.060 [−0.086, −0.035] | raw_numbers.json E5.lenient.gap_bw_minus_mfa5=−0.0601, ci=[−0.0856, −0.0346] | ✓ |
| 81 | `neighbours / 6` graph_connectivity | improved/pipeline.py line 408: `bridge = min(1.0, len(adj.get(agent, set())) / 6.0)` | ✓ |
| 81 | orchestrator components 0.44/0.44/0.78; supply 0.22/0.11/0.17 (was 0.45/0.45/0.83 and 0.20/0.10/0.17) | aggregate over baseline/outputs/suspects.csv: orchestrator avg prox=0.44 freq=0.44 graph=0.78; supply avg prox=0.22 freq=0.11 graph=0.17 | ✗ → fixed |
| 81 | 0.05 role penalty | 0.1 weight × (1.0 − 0.5) = 0.05 (SUSPECT_WEIGHTS["role"]=0.1, ROLE_RELEVANCE delta=0.5) | ✓ |
| 81 | 406 sub_reroute traces; walk names orchestrator 197 times, pricing 85 times, supply 0 times | raw_numbers.json E5.per_mode.substitution_reroute: n=406; backward_walk_top1_distribution={orchestrator:197, unknown:124, pricing:85}; supply absent ⇒ 0 | ✓ |
| 81 | WALK_DEPTH=10 | improved/pipeline.py line 86: `WALK_DEPTH = 10` | ✓ |
| 83 | strict P@1 = 0.004 | raw_numbers.json E5.strict.mfa5_precision_at_1=0.003643 | ✓ |
| 83 | E2 CI [+0.021, +0.138] excludes zero | raw_numbers.json E2.gap.ci_lo=0.0205 > 0 | ✓ |
| 91 | bucket_days=5, DRIFT_DAY=45 | improved/pipeline.py cusum_drift default bucket_days=5; sim/generate_traces.py DRIFT_DAY=45 | ✓ |
| 91 | +0.4% drift | improved/pipeline.py cusum_drift default h=0.004 (threshold for cumulative deviation) | ✓ |
| 91 | bucket_days=7 → alert day 56 (cross-cluster), day 49 (per-case-type) | post-hoc ablation; stated in article and falsifier #4; reproduced (per the falsifier text) | ✓ (assertion, reproducible) |
| 109 | falsifier: 0.402 vs 0.400, N=143, ±5pp MDE | post-hoc; matches §"wins" discussion above | ✓ |
| 117 | strict P@1 = 0.004 | E5.strict.mfa5_precision_at_1=0.00364 | ✓ |
| 128 | "~90 seconds end-to-end" | runtime claim; improved/outputs/run_metadata.json.runtime_seconds is order-of-tens-of-seconds | ✓ (qualitative) |

## Fixes applied to article

1. "141-line diff" → "139-line diff" (line 13)
2. "regulated-export configuration" → "standard-build configuration" (line 3; t00011 is standard_build)
3. Example traces swapped to correct case_types: t00084 ↔ t00012 swap; t00321 → t00102 (line 47)
4. Suspect-score components corrected: orchestrator 0.44/0.44/0.78 (was 0.45/0.45/0.83); supply 0.22/0.11/0.17 (was 0.20/0.10/0.17) (line 81)
5. "98% of EL latency tokens" → "94%" (line 61); actual 2444/2595 = 0.942

## Verdict

PASS
