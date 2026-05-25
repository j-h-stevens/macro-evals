# Held-out validation (80/20 split)

Seed 42. Train: 3982; held-out: 1018 (partition by `hash(trace_id) % 5 == 0`).

Pipelines re-fit on train only. Held-out traces are embedded with the same MiniLM model, projected with `UMAP.transform` against the train-fit reducer, and assigned via `hdbscan.approximate_predict` against the train-fit HDBSCAN. Majority cluster per failure mode is computed on the TRAIN partition, then applied unchanged to the held-out set.

Train cluster counts: baseline 59 (noise 77); improved 84 (noise 222).  Held-out noise (approximate_predict): baseline 44 / 1018; improved 64 / 1018.

## Per-mode recall@cluster: in-sample (train) vs held-out (test)

| Mode | Baseline in-sample | Baseline held-out | Improved in-sample | Improved held-out |
|---|---|---|---|---|
| substitution_reroute | 0.215 (n=331) | 0.253 (n=75) | 0.215 (n=331) | 0.253 (n=75) |
| compliance_skipped_under_tariff | 0.166 (n=199) | 0.104 (n=48) | 0.211 (n=199) | 0.104 (n=48) |
| stale_quote_slow_pricing | 0.127 (n=150) | 0.156 (n=45) | 0.047 (n=150) | 0.044 (n=45) |
| pricing_drift | 0.168 (n=2124) | 0.153 (n=542) | 0.053 (n=2124) | 0.054 (n=542) |
| escalation_loop | 0.940 (n=116) | 0.370 (n=27) | 0.310 (n=116) | 0.259 (n=27) |
| random_noise_failure | 0.258 (n=229) | 0.244 (n=82) | 0.249 (n=229) | 0.232 (n=82) |

## E2 (H1 temporal, stale_quote_slow_pricing)

- In-sample (train 80%): baseline 0.127, improved 0.047, gap -0.080.
- Held-out (test 20%): baseline 0.156, improved 0.044, gap -0.111 [-0.244, +0.000] (paired bootstrap on held-out hit indicators).
- In-sample verdict: **REFUTED**.  Held-out verdict: **REFUTED**.

The article's E2 verdict ('DIRECTION CONFIRMED') maps to REFUTED on held-out data.

## E5 (backward walk vs MFA-5 on held-out structural failures)

- Held-out structural traces (substitution_reroute + escalation_loop): n=99.
- Strict ground truth:
  - MFA-5 precision@1: 0.000 [0.000, 0.000]
  - Backward walk precision@1: 0.000 [0.000, 0.000]
  - Gap (walk - MFA-5): +0.000 [+0.000, +0.000]  => **NULL**
- Lenient ground truth (escalation_loop GT = {compliance, release}):
  - MFA-5 precision@1: 0.202 [0.131, 0.273]
  - Backward walk precision@1: 0.101 [0.051, 0.162]
  - Gap (walk - MFA-5): -0.101 [-0.182, -0.030]  => **MFA-5 BEATS WALK**

Per-mode (strict, held-out):
  - substitution_reroute: n=75, MFA-5=0.000, walk=0.000
  - escalation_loop: n=27, MFA-5=0.000, walk=0.000

In-sample comparison (from `eval/raw_numbers.json`): strict gap -0.004 [-0.009, +0.000]. The article's verdict is 'walk loses to MFA-5'. 
**Held-out verdict is NULL: the gap is no longer significant out of sample.**

_Runtime: 61.2s. Written by `eval/held_out.py`._