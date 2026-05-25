# 2×2×2 factorial: latency × absence × CUSUM

Each mechanism toggled on/off independently. Recall = recall@top-cluster on the
full 5,000-trace dataset, seed 42, UMAP and HDBSCAN parameters held constant
(min_cluster_size=20, n_neighbors=15, n_components=5).

CUSUM operates on observable price returns post-clustering and does **not**
feed into the clustering geometry. Verified by inspection of
`improved/pipeline.py` (`cusum_drift` is called after `cluster_hdbscan` and the
returns are written to a separate `drift_alerts.csv`; cluster labels are
unchanged regardless of whether CUSUM is enabled). Therefore the four
CUSUM-on rows (`001`, `011`, `101`, `111`) have identical recall@top-cluster
to their CUSUM-off counterparts (`000`, `010`, `100`, `110`). They are listed
explicitly below to keep the factorial table honest.

Convention: `LAC` where `L`=latency tokens, `A`=absence tokens, `C`=CUSUM.

| LAC | latency | absence | CUSUM | sub_reroute | CSK | stale_quote | pricing_drift | escalation_loop | random_noise |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 000 | off | off | off | 0.222 | 0.194 | 0.051 | 0.024 | 0.252 | 0.138 |
| 001 | off | off | **on** | 0.222 | 0.194 | 0.051 | 0.024 | 0.252 | 0.138 |
| 010 | off | **on** | off | 0.143 | 0.194 | 0.051 | 0.023 | 0.343 | 0.296 |
| 011 | off | **on** | **on** | 0.143 | 0.194 | 0.051 | 0.023 | 0.343 | 0.296 |
| 100 | **on** | off | off | 0.209 | 0.174 | 0.133 | 0.026 | 0.420 | 0.325 |
| 101 | **on** | off | **on** | 0.209 | 0.174 | 0.133 | 0.026 | 0.420 | 0.325 |
| 110 | **on** | **on** | off | 0.387 | 0.190 | 0.133 | 0.047 | 0.699 | 0.241 |
| 111 | **on** | **on** | **on** | 0.387 | 0.190 | 0.133 | 0.047 | 0.699 | 0.241 |

## Main effects (averaging over off levels of the other two)

Per failure mode, the latency main effect (L=on minus L=off, holding A=off):

| mode | ΔL \| A=off | ΔL \| A=on | ΔA \| L=off | ΔA \| L=on | Interaction (ΔL·ΔA) |
|---|---:|---:|---:|---:|---:|
| substitution_reroute | −0.013 | +0.244 | −0.079 | +0.178 | +0.257 |
| compliance_skipped_under_tariff | −0.020 | −0.004 | 0.000 | +0.016 | +0.016 |
| stale_quote_slow_pricing | +0.082 | +0.082 | 0.000 | 0.000 | 0.000 |
| pricing_drift | +0.002 | +0.024 | −0.001 | +0.021 | +0.022 |
| escalation_loop | +0.168 | +0.356 | +0.091 | +0.279 | +0.188 |
| random_noise_failure | +0.187 | −0.055 | +0.158 | −0.084 | −0.242 |

(ΔL \| A=off = recall(1A0,A=0) − recall(0A0,A=0); analogously for others.
Interaction = ΔL\|A=on − ΔL\|A=off, equal to ΔA\|L=on − ΔA\|L=off by symmetry.)

## Per-mechanism vs interaction effects

**Latency tokens (L) carry most of the headline `escalation_loop` gain on
their own**: enabling latency with absence off lifts EL recall from 0.252 to
0.420 (+17pp), and adding absence on top lifts it the rest of the way to
0.699. The +45pp full effect therefore decomposes into roughly +17pp from
latency alone, +9pp from absence alone, and +19pp from the
latency×absence interaction (the bucketed `lat:fast` motif co-occurring with
absence tokens reinforces a cluster boundary that neither mechanism produces
on its own). The "uniform-motif" mechanism flagged in the article is
necessary but not sufficient — without absence tokens to glue the cluster
together at one end, EL gains are about 40% of the headline value.

**Absence tokens (A) carry no `compliance_skipped_under_tariff` signal in
any combination.** Toggling A with L off changes CSK recall by 0.000;
toggling A with L on changes it by +0.016. The article's H2-inert conclusion
holds at the factorial level: there is no combination of the three
mechanisms that produces meaningful CSK recall improvement. The mechanism
targeted at CSK does not work, with or without the other two.

**`substitution_reroute` is the strongest interaction case**: latency alone
*hurts* sub_reroute (−0.013), absence alone hurts sub_reroute (−0.079), but
together they yield +0.165. This is consistent with the cluster-116
dustbin reading: the two mechanisms only co-pull sub_reroute traces into a
shared cluster when both are active, and that shared cluster also drags in
pricing_drift and EL. The "gain" is an emergent property of the joint
encoding, not of either token type in isolation.

**`random_noise_failure` interacts negatively**: each mechanism alone lifts
recall (+0.187 from L, +0.158 from A), but together the gain shrinks to
+0.103. The two mechanisms compete for the same noise-clustering capacity
of the embedder.

**CUSUM (C) has zero effect on clustering-based recall by construction**;
its contribution to E4 (drift detection at day 45) is orthogonal and not
visible in this table. The factorial confirms the article's "CUSUM is
genuinely orthogonal" claim: no interaction with L or A is possible because
CUSUM does not modify the document, the embedding, or the clusterer.

## Honest caveat

The headline +45pp EL gain reported in the article is the 110→000
difference, not the latency-alone effect. A reader who wants to attribute
the gain to "latency tokens" specifically should look at row 100 vs 000
(+17pp). The remaining ~60% of the headline gain is a non-additive
interaction with absence tokens.
