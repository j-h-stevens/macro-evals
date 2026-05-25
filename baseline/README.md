# Baseline pipeline

Faithful reproduction of the OpenAI "Macro Evals for Agentic Systems"
cookbook, applied to `sim/data/traces.jsonl` (5,000 labelled traces).

The pipeline is intentionally not "improved." Where the cookbook leaves a
choice unspecified, we picked the most common community default and noted
the choice as **undefended** with a citation back to `research/source-claims.md`.
The Improver may change these; the Statistician will measure the gap.

## Reproduce

```bash
python3 -m venv ../.venv
../.venv/bin/pip install sentence-transformers umap-learn hdbscan scikit-learn numpy pandas
../.venv/bin/python pipeline.py
```

Outputs land in `baseline/outputs/`. End-to-end runtime on a CPU-only
laptop: **~31 seconds** (well under the 10-minute budget).

## Hyperparameter table

| Stage | Parameter | Value | Source-claims citation | Status |
|---|---|---|---|---|
| Embedding | model | `sentence-transformers/all-MiniLM-L6-v2` | §10.2.1, §12.1.1 | undefended — cookbook silent, MiniLM is the common BERTopic default |
| Embedding | dim | 384 | derived from model | undefended |
| UMAP | n_neighbors | 15 | §12.1.4 | undefended — BERTopic default |
| UMAP | n_components | 5 | §12.1.4 | undefended — BERTopic default |
| UMAP | min_dist | 0.0 | §12.1.4 | undefended — BERTopic default |
| UMAP | metric | cosine | §12.1.3 | undefended — BERTopic default |
| UMAP | random_state | 42 | §6.7.4 | specified |
| HDBSCAN | min_cluster_size | 20 | §6.7.1, §12.4.3 | undefended — task spec; cookbook says 24 default but adaptive |
| HDBSCAN | min_samples | 5 | §12.2.1 | undefended — BERTopic default |
| HDBSCAN | metric | euclidean | §12.2.1 | undefended — BERTopic default |
| c-TF-IDF | top_n_terms | 10 | §6.7.3 | task spec (cookbook = 8) |
| Severity | hard_failure | 3.0 | §5.4.1, §10.5.1 | undefended |
| Severity | review | 2.0 | §5.4.1 | undefended |
| Severity | completion_with_finding | 1.0 | §5.4.1 | undefended; bucket is empty for this dataset (no findings_count column) |
| Suspect | proximity weight | 0.4 | §8.5.1, §10.5.2 | undefended |
| Suspect | frequency weight | 0.3 | §8.5.1 | undefended |
| Suspect | graph_connectivity weight | 0.2 | §8.5.1 | undefended |
| Suspect | role_relevance weight | 0.1 | §8.5.1 | undefended |
| Suspect | walk depth (N) | 10 | §12.4.2 | task spec (cookbook = 5) |
| Suspect | role heuristic | orchestrator = 0.5, others = 1.0 | §8.5.5, §12.1.4 | undefended — cookbook silent on which roles count |
| Seed | global | 42 | §6.7.4 | specified |

## Hard constraints honored

1. **No `_raw_price_usd` or any underscore-prefixed field** is read by the
   pipeline. `_strip_underscore_fields` recursively scrubs the event
   payload before document construction or any feature extraction.
   *Justification:* SCHEMA.md flags these as ground-truth helpers for the
   generator's integrity check; a faithful production pipeline cannot see
   them. Reading `_raw_price_usd` is exactly what hypothesis **H3**
   identifies as the cheat that would defeat its prediction — the Improver
   may add a CUSUM monitor that uses it; the baseline must not.

2. **No `latency_ms` features in document construction.** Latency is
   dropped from every event when the document string is built.
   *Justification:* The cookbook's `doc_structured_summary` enumerates
   scenario, routing, state transitions, handoffs, findings, and terminal
   state (§5.6.3); latency is absent from that list. Hypothesis **H1**
   predicts this omission makes `stale_quote_slow_pricing` unrecoverable.

3. **No absence / expected-event features.** The document encodes events
   that occurred. Nothing in the pipeline references a `ROUTING_CONTRACT`
   or "expected agent set" lookup.
   *Justification:* Faithful to §5.6.3 — the cookbook does not describe a
   counterfactual document construction. Hypothesis **H2** predicts this
   makes `compliance_skipped_under_tariff` unrecoverable.

4. **No trace timestamps used for temporal modelling.** `day`, `t_ms`,
   and `prompt_version` are not features. (`day` is present in trace
   metadata but never reaches the document, the embedding, the
   clustering, or the impact/lift computation.)
   *Justification:* The cookbook label pipeline is
   case_type → run_outcome → eval_finding → behavior_pattern (§5.2.1).
   No time axis appears. Hypothesis **H3** predicts this makes
   `pricing_drift` undetectable.

## Outputs

All under `baseline/outputs/`:

| File | What it is |
|---|---|
| `clusters.jsonl` | One row per trace: `trace_id`, `cluster_id`, `document`, `umap_coords`. |
| `cluster_labels.json` | `cluster_id` → `{top_terms, size, prevalence, severity_distribution, impact_score, high_impact}`. |
| `cluster_x_failure_mode.csv` | Confusion matrix: rows = clusters, cols = ground-truth failure modes + `clean`. Statistician input. |
| `lift.csv` | `(cluster, case_type)` → `lift = P(cluster|case_type)/P(cluster)`. |
| `suspects.csv` | High-impact clusters → ranked suspect agents with proximity, frequency, graph_connectivity, role_relevance, and final suspect_score. |
| `run_metadata.json` | seed, all hyperparameters, library versions, platform, runtime. |

The confusion matrix is the **only** place in the pipeline that touches
`failure_modes`; it is written for the Statistician and not used as
input to any earlier stage.

## Latest run summary

- Traces: 5,000
- Clusters discovered: 118
- HDBSCAN noise (cluster = -1): 218 traces (4.4%)
- Runtime: ~31 seconds

## Judgement calls

A handful of decisions had no cookbook anchor; recorded here so the
Improver and Statistician do not re-litigate them implicitly.

1. **Severity bucket for `outcome=completed`.** The cookbook's
   `completion_with_finding` (weight 1.0) requires a `findings_count`
   column we do not have. We mapped all `completed` to
   `successful_completion` (weight 0.0). Impact scores for clusters
   dominated by completed traces are therefore zero. This is faithful to
   the schema we were given; if the Improver adds a finding-detector this
   bucket gets repopulated.
2. **Focus-event detection.** The cookbook (§8.3.1) lists "review/finding
   marker, failure-related status, or late-stage decision event" without
   a precise rule. We picked: first event of `type=='failure'`, else
   first event of `type=='signal'`, else the last event when outcome ∈
   {blocked, failed, review}. Traces whose outcome is `completed` and
   that have no signal event get no anchor and are skipped by the walk.
3. **Graph_connectivity definition.** Cookbook says "bridge rewards
   events that connect parts of the execution graph" (§8.5.4). We use a
   simple unique-neighbour count in the window's call/handoff graph,
   normalized by 6. We did not implement betweenness centrality — that
   would be an improvement, flagged for the Improver.
4. **Role heuristic.** Cookbook (§8.5.5) says role rewards "plausibly
   related" agents but lists no mapping. We treat orchestrator as 0.5 and
   all specialists as 1.0. A domain-specific mapping (e.g. boost
   `pricing` for pricing failures) would be an improvement.
5. **High-impact filter for the walk.** The task spec says "for each
   trace in a high-impact cluster"; we operationalised "high-impact" as
   impact_score ≥ median of non-noise clusters' impact_scores.

See `baseline/notes-for-improver.md` for things we deliberately did not
do.

## Library versions

See `outputs/run_metadata.json` after running. Captured at run time so
the file always matches the last reproduction.
