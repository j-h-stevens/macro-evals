# Notes for the Improver

Things the Baseline implementer noticed but did NOT do, because doing
them would compromise the faithful-baseline contract. The Improver gets
to do these.

## Document construction

- **Latency tiering.** Inject a per-event token like `pricing_return_slow`
  derived from `latency_ms` thresholds. Directly targets H1
  (`stale_quote_slow_pricing`). See hypotheses.md H1 §"Proposed Fix" for
  exact tier breakpoints.
- **Expected-but-absent tokens.** Build a `(case_type, env_signal) ->
  required_agent` lookup and emit `MISSING_COMPLIANCE` etc. when the
  required agent did not run. Directly targets H2. See hypotheses.md H2
  §"Proposed Fix".
- **Event-count features.** Total events, unique agents, max handoff
  depth — these are cheap and the cookbook does not forbid them.
- **Status-token bigrams.** Concatenate consecutive `agent=status`
  transitions ("`compliance=pass supply=substitute`") so HDBSCAN sees
  short n-grams of state, not just bag-of-tokens.

## Beyond the discovery pipeline

- **CUSUM drift detector.** A separate monitor that operates on
  time-bucketed pricing-return numerics. Reads `_raw_price_usd` (or, in
  production, an external pricing oracle). Orthogonal to clustering.
  Directly targets H3 (`pricing_drift`).
- **Per-failure-mode evaluator.** The Statistician will already compute
  recall@cluster from `cluster_x_failure_mode.csv`. The Improver should
  re-emit that confusion matrix after their changes; the comparison
  baseline→improved on identical metrics is the article's central
  evidence.

## Suspect walk

- **Betweenness centrality** for the `bridge` component, instead of the
  unique-neighbour proxy we used.
- **Domain-specific role mapping.** E.g. cluster keyword `pricing` →
  boost `pricing` agent's role score for that cluster. Currently we use a
  static map (orchestrator=0.5, others=1.0).
- **MFA-N comparison.** Implement the two-line
  most-frequent-agent-in-last-N attribution from hypotheses.md H4 and
  compare precision@1. The article needs this number to either back or
  retract the cookbook's implicit causal-attribution claim.

## Hyperparameter choices the baseline locked in

- `min_cluster_size = 20` (cookbook says 24 adaptive; spec said 20).
- `top_n_terms = 10` (cookbook says 8; spec said 10).
- `walk_depth = 10` (cookbook says 5; spec said 10).

If the Improver runs a sensitivity sweep on these (cookbook ablation
gaps §13.1.4, §13.1.5, §13.3.4), the article gets a cheap point.

## Things we explicitly did NOT do

- Did not use `latency_ms`, `t_ms`, `day`, or `prompt_version` as
  features.
- Did not read any underscore-prefixed field.
- Did not include positive-pattern discovery (cluster on successful
  traces). Cookbook §6.6.1 filters discovery to failures by default; we
  did NOT filter because the task spec asks for the confusion matrix
  across all 5,000 traces, and filtering would zero out cells the
  Statistician needs. This is a faithful adaptation, not a deviation —
  the cookbook's filter is a discovery-input choice, not an outputs
  choice. The Improver may want to re-run discovery on the filtered
  population as well, for a sharper failure-pattern view.
