# Macro Evals, Audited

A pre-registered synthetic regression test of OpenAI's [*Macro Evals for Agentic Systems*](https://developers.openai.com/cookbook/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems) cookbook, pending independent replication.

**Status:** v1.0 pre-release. The seed sweep across {7, 42, 137, 2024, 31337} is scheduled to complete by 2026-07-01. Until then, every point estimate in [`article.md`](./article.md) is one seed.

## Headline findings (post meta-audit, conditional on this workload)

- **The cookbook's pipeline catches the "easy" failures at 22–25% recall@cluster.** Structural failures the cookbook implies its pipeline handles well land far below the 50% sanity threshold our pre-registration named.
- **The "improved" pipeline's escalation_loop gain is artifactual.** A constant-`lat:tick` ablation collapses the +45pp gain to baseline; the active ingredient is consistent with uniform-motif repetition, not with latency information being lifted into the geometry.
- **The cookbook's backward suspect walk loses to a two-line heuristic** ("most frequent agent in last 5 events") on hub-and-spoke topologies. The four-component scoring formula is structurally biased toward hubs.
- **Document construction is the load-bearing design decision in the cookbook's pipeline template.** Treated as preprocessing in the cookbook; in fact it decides what the embedder sees, what the clusterer can find, and what the suspect walker can attribute.

## How to reproduce (≤ 5 minutes wall time on a CPU laptop)

```bash
git clone https://github.com/j-h-stevens/macro-evals.git
cd macro-evals
uv sync   # or: pip install -r requirements.lock
bash appendix/reproduce.sh
```

Every number in [`article.md`](./article.md) traces to one of:
- [`eval/raw_numbers.json`](./eval/raw_numbers.json)
- [`baseline/outputs/cluster_x_failure_mode.csv`](./baseline/outputs/cluster_x_failure_mode.csv)
- [`improved/outputs/cluster_x_failure_mode.csv`](./improved/outputs/cluster_x_failure_mode.csv)

If you find a number in the article that does not match the artifacts, the artifacts are right and the article is wrong. File an issue.

## How this work was reviewed before release

This audit was adversarially reviewed by a 60-named-expert panel (statisticians, ML researchers, systems engineers, writers/epistemologists) and two meta-validators. Their findings live under [`meta/`](./meta/):

- [`meta/convergence.md`](./meta/convergence.md) — the 10 convergent legitimate critiques and 7 collective blind spots, with the ranked pre-release action plan.
- [`meta/legitimacy_audit.md`](./meta/legitimacy_audit.md) — re-grading of the panels' verdicts; 33 of 60 critiques downgraded to SPECIOUS because the article already discloses what panelists complained about.

The pre-registration is at [`eval/preregistration.md`](./eval/preregistration.md). The five dated falsifiers the article publishes against itself are in `article.md` §"Five dated falsifiers."

## How to engage with this work

1. **Run the experiments**, find a number that disagrees, file an issue.
2. **Run one of the five dated falsifiers** in §10 of the article and PR your results. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).
3. **Add a topology** to `sim/generate_traces.py` other than hub-and-spoke and re-run; the panel argued our walk-vs-MFA-5 finding is topology-conditional and we agree.
4. **Swap the embedder** (text-embedding-3-small, bge-large, jina-v3) and re-run; Falsifier #5 lives or dies on this.

## Repository layout

```
article.md                      The audit, as prose
sim/                            Synthetic-trace generator + 5,000-trace dataset
baseline/                       Faithful implementation of the cookbook's pipeline
improved/                       141-line diff adding latency tokens, absence tokens, CUSUM
baseline_handfeature/           Carmack hand-feature baseline for clustering
eval/                           Pre-registration, metrics, results, raw numbers
research/                       Verbatim claim inventory from the cookbook
red-team/                       Forensic investigation into why fixes failed
meta/                           60-expert adversarial review + two meta-validators
figures/                        Static figures
appendix/                       reproduce.sh, dependency lockfile
```

## License

MIT. See [`LICENSE`](./LICENSE). The cookbook authors are encouraged to lift any of the harness for their own ablations and would be credited in any follow-on work.

## Citation

See [`CITATION.cff`](./CITATION.cff).
