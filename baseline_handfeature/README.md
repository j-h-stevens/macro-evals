# Hand-feature baseline

A trivial 20-dimensional feature vector + KMeans, matched on cluster count
to the improved HDBSCAN output (n=121, random_state=42). Bypasses MiniLM,
UMAP, HDBSCAN, and c-TF-IDF entirely.

## Motivation

From the panel critique (`meta/convergence.md` C5, Carmack's lead voice in
Panel C): the cookbook's pipeline is MiniLM -> UMAP -> HDBSCAN ->
c-TF-IDF -> impact x lift -> backward walk. Carmack's critique was that
no hand-feature baseline had been tried; without one, every comparison
inside the cookbook's machinery is auditing decoration. Strip the
framing, ask whether ~20 hand-built features can match the embedding
pipeline on the six pre-registered failure modes.

If this baseline ties or beats the cookbook pipeline, the cookbook's
sentence-encoder stack is not earning its complexity on this workload.

## Feature vector (20 dims total)

Read from each trace JSON; no event-text inspection beyond agent names,
edge structure, and latency:

| Feature                          | Dims | Source                                           |
|----------------------------------|------|--------------------------------------------------|
| `case_type` one-hot              | 5    | trace.case_type                                  |
| `outcome` one-hot                | 4    | completed/review/blocked/failed (blocked unused) |
| `did_compliance_fire`            | 1    | any event with agent=="compliance"               |
| `n_distinct_agents` / 7          | 1    | distinct agents across events                    |
| `log_event_count`                | 1    | log(1 + len(events))                             |
| `max_latency_ms` / 1000, clip 10 | 1    | per-event latency_ms                             |
| `has_loop`                       | 1    | any (caller, callee) edge repeats >= 2 times     |
| top-K agent bigrams (K=8)        | 8    | normalized per-trace bigram counts               |

In our generator the agent graph is hub-and-spoke around `orchestrator`,
so only six distinct bigrams ever appear; the remaining two slots are
zero. We kept K=8 for clarity rather than re-tuning.

## Clustering

`sklearn.cluster.KMeans(n_clusters=121, n_init=10, random_state=42)`.
Cluster count is read from `improved/outputs/cluster_labels.json` to
match the comparator.

## Outputs

- `outputs/cluster_x_failure_mode.csv` -- same schema as
  `baseline/outputs/cluster_x_failure_mode.csv` and
  `improved/outputs/cluster_x_failure_mode.csv`.
- `outputs/clusters.jsonl` -- `{trace_id, cluster_id}` per line.
- `outputs/run_metadata.json` -- seed, n_clusters, feature dim, per-mode
  recall@cluster, library versions, runtime.

## Result (seed 42)

Per-mode recall@cluster on the full 5,000-trace dataset:

| Mode                              | Baseline (MiniLM) | Improved (MiniLM+ext) | Hand-feature (this) |
|-----------------------------------|-------------------|-----------------------|---------------------|
| substitution_reroute              | 0.222             | 0.391                 | 0.281               |
| compliance_skipped_under_tariff   | 0.190             | 0.186                 | 0.194               |
| stale_quote_slow_pricing          | 0.051             | 0.133                 | 0.087               |
| pricing_drift                     | low cluster signal| low cluster signal    | 0.087               |
| escalation_loop                   | 0.252             | 0.699                 | 0.168               |
| random_noise_failure              | low               | low                   | 0.100               |

(Cookbook numbers from `eval/raw_numbers.json`. The handfeature column is
from `outputs/run_metadata.json` in this directory.)

Reading: the hand-feature baseline matches MiniLM+UMAP on H2 (CSK), is
within a few points on substitution_reroute, but loses materially on
escalation_loop (0.168 vs 0.699), where the improved pipeline's
latency-bucket tokens build a uniform-motif signature inside loops that
no 20-dim hand vector reproduces. It also loses on stale_quote where the
improved pipeline has latency information.

The honest read: the hand-feature baseline is *not* a clean win. It
contests the cookbook pipeline on three of six modes and clearly loses
on the loop-detection failure mode that the improved pipeline targets.
But it sets a floor: any cookbook recall number below 0.20 is no better
than what 20 hand-built features deliver. Roughly half the
recall@cluster numbers in the audit are inside that band.

This does not refute the cookbook's pipeline; it brackets it. The
cookbook earns its complexity on `escalation_loop` and `stale_quote` and
does not earn it elsewhere.

## Reproduce

```
python baseline_handfeature/pipeline.py
```

Reads `sim/data/traces.jsonl` and `improved/outputs/cluster_labels.json`;
writes the three files in `outputs/`. Deterministic at seed 42.
