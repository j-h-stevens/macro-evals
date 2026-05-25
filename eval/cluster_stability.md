# HDBSCAN min_cluster_size perturbation

UMAP coordinates held fixed (loaded from `improved/outputs/clusters.jsonl`, random_state=42 throughout). HDBSCAN re-clustered at min_cluster_size ∈ {10, 15, 20, 25, 30}; min_samples=5, metric=euclidean. Recall = fraction of mode's traces falling in that mode's plurality cluster (excluding noise).

## Cluster counts

| min_cluster_size | n_clusters | n_noise |
|---|---:|---:|
| 10 | 195 | 135 |
| 15 | 145 | 198 |
| 20 | 121 | 221 |
| 25 | 103 | 275 |
| 30 | 89 | 351 |

## Recall@top-cluster by failure mode

| Failure mode | n | mcs=10 | mcs=15 | mcs=20 | mcs=25 | mcs=30 |
|---|---|---|---|---|---|---|
| substitution_reroute | 406 | 0.076 (c=191) | 0.158 (c=142) | 0.387 (c=116) | 0.387 (c=99) | 0.387 (c=85) |
| compliance_skipped_under_tariff | 247 | 0.117 (c=4) | 0.117 (c=4) | 0.190 (c=73) | 0.202 (c=72) | 0.393 (c=46) |
| stale_quote_slow_pricing | 195 | 0.077 (c=55) | 0.133 (c=47) | 0.133 (c=46) | 0.133 (c=42) | 0.067 (c=77) |
| pricing_drift | 2666 | 0.028 (c=11) | 0.028 (c=11) | 0.047 (c=116) | 0.047 (c=99) | 0.047 (c=85) |
| escalation_loop | 143 | 0.210 (c=168) | 0.287 (c=122) | 0.699 (c=116) | 0.699 (c=99) | 0.699 (c=85) |
| random_noise_failure | 311 | 0.084 (c=172) | 0.190 (c=110) | 0.241 (c=96) | 0.325 (c=70) | 0.325 (c=62) |

## Stability commentary

Recall is not stable under min_cluster_size perturbation: **substitution_reroute** swings 0.08→0.39 (Δ=0.31); **compliance_skipped_under_tariff** swings 0.12→0.39 (Δ=0.28); **escalation_loop** swings 0.21→0.70 (Δ=0.49); **random_noise_failure** swings 0.08→0.32 (Δ=0.24). This means the recall@top-cluster numbers reported in the article are conditional on the specific HDBSCAN hyperparameter we chose (min_cluster_size=20) and would shift materially under a defensible alternative. This is an additional caveat beyond the seed-stability caveat already stated in §"Caveats the reader needs before the results"; any production team using this pipeline should sweep this parameter before trusting any single recall number.
