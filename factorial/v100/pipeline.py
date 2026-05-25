"""
Improved pipeline: baseline + three surgical extensions for H1/H2/H3.
  A) latency-bucket tokens per event   (build_document, addresses H1)
  B) absent-agent tokens per case_type (build_document, addresses H2)
  C) CUSUM drift detector on observable price_usd (separate module, H3)
All other hyperparameters and stages match baseline/pipeline.py.
"""

from __future__ import annotations

import json
import os
import platform
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Determinism: set seeds before importing any RNG-using library.
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
os.environ.setdefault("PYTHONHASHSEED", str(SEED))

import hdbscan  # noqa: E402
import sklearn  # noqa: E402
import umap  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from sklearn.feature_extraction.text import CountVectorizer  # noqa: E402

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
TRACES_PATH = PROJECT / "sim" / "data" / "traces.jsonl"
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Hyperparameters (see README for citations)
# -----------------------------------------------------------------------------

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

UMAP_PARAMS = dict(
    n_neighbors=15,
    n_components=5,
    min_dist=0.0,
    metric="cosine",
    random_state=SEED,
)

HDBSCAN_PARAMS = dict(
    min_cluster_size=20,
    min_samples=5,
    metric="euclidean",
)

TOP_N_TERMS = 10  # c-TF-IDF terms per cluster

# Severity weights (source-claims §5.4.1 -- undefended assertion).
SEVERITY_WEIGHTS = {
    "hard_failure": 3.0,
    "review": 2.0,
    "completion_with_finding": 1.0,
    "successful_completion": 0.0,
}

# Outcome -> outcome_group (source-claims §5.3.1).
OUTCOME_GROUP_MAP = {
    "completed": "successful_completion",
    "review": "review",
    "blocked": "hard_failure",
    "failed": "hard_failure",
}

# Backward-walk suspect scoring weights (source-claims §8.5.1).
SUSPECT_WEIGHTS = dict(proximity=0.4, frequency=0.3, bridge=0.2, role=0.1)
WALK_DEPTH = 10  # task spec N=10

# Domain heuristic for role component (source-claims §8.5.5 -- undefended).
# Cookbook says "role rewards events whose agent/tool role is plausibly
# related to the finding." We treat all non-orchestrator specialists as
# plausibly causal (1.0) and orchestrator as routing-only (0.5).
ROLE_RELEVANCE = defaultdict(
    lambda: 1.0,
    {"orchestrator": 0.5},
)


# -----------------------------------------------------------------------------
# 1. Document construction
# -----------------------------------------------------------------------------

UNDERSCORE_KEY_RE = re.compile(r"^_")


def _strip_underscore_fields(obj: Any) -> Any:
    """Recursively strip underscore-prefixed keys. Ground-truth labels live
    behind that convention (SCHEMA.md); the pipeline must not see them."""
    if isinstance(obj, dict):
        return {
            k: _strip_underscore_fields(v)
            for k, v in obj.items()
            if not UNDERSCORE_KEY_RE.match(k)
        }
    if isinstance(obj, list):
        return [_strip_underscore_fields(v) for v in obj]
    return obj


def derive_outcome_group(outcome: str) -> str:
    return OUTCOME_GROUP_MAP.get(outcome, "successful_completion")


def derive_severity_label(trace: dict) -> str:
    """Map a trace to {hard_failure, review, completion_with_finding,
    successful_completion}.

    Cookbook (source-claims §5.5.2) flags has_failure when outcome,
    validation, or findings indicate trouble. Our schema has no separate
    validation or findings_count column, so completion_with_finding is
    unused in the faithful mapping (documented in README)."""
    return derive_outcome_group(trace["outcome"])


def _latency_bucket(ms: int) -> str:
    if ms < 500: return "lat:fast"
    if ms < 2000: return "lat:normal"
    if ms < 5000: return "lat:slow"
    return "lat:stalled"


# Extension B: expected agent set per case_type. Derived from sim data
# exploration: all five case_types activate {orchestrator, pricing, supply,
# scheduling, release} 100% and compliance 95%+ in clean traces. factory
# appears in supplier_substitution paths only.
EXPECTED_AGENTS = {
    "standard_build":        {"orchestrator","pricing","supply","compliance","scheduling","release"},
    "supplier_substitution": {"orchestrator","pricing","supply","compliance","factory","scheduling","release"},
    "regulated_export":      {"orchestrator","pricing","supply","compliance","scheduling","release"},
    "expedited_delivery":    {"orchestrator","pricing","supply","compliance","scheduling","release"},
    "custom_configuration":  {"orchestrator","pricing","supply","compliance","scheduling","release"},
}


def build_document(trace: dict) -> str:
    """Baseline structured summary PLUS:
      A) per-event latency-bucket token  -- addresses H1 temporal blindness
      B) absent-agent tokens per case_type -- addresses H2 omission blindness
    All other token construction matches baseline byte-for-byte."""
    events = _strip_underscore_fields(trace["events"])

    parts: list[str] = []
    parts.append(f"case_type:{trace['case_type']}")
    env = sorted(set(trace.get("env_signals", [])))
    if env:
        parts.append("env:" + ",".join(env))

    seq_tokens: list[str] = []
    transitions: list[str] = []
    activated: set[str] = set()
    for ev in events:
        agent = ev.get("agent", "?")
        etype = ev.get("type", "?")
        tool = ev.get("tool")
        to = ev.get("to")
        activated.add(agent)

        if etype in ("call", "handoff"):
            tok = f"{agent}->{to or '?'}"
            if tool:
                tok += f":{tool}"
            seq_tokens.append(tok)
        elif etype == "return":
            tok = f"{agent}_return"
            if tool:
                tok += f":{tool}"
            status = (ev.get("value") or {}).get("status")
            if status:
                tok += f"={status}"
                transitions.append(f"{agent}={status}")
            seq_tokens.append(tok)
        elif etype == "tool":
            tok = f"{agent}_tool"
            if tool:
                tok += f":{tool}"
            seq_tokens.append(tok)
        elif etype == "signal":
            note = (ev.get("note") or "signal").replace(" ", "_")
            seq_tokens.append(f"{agent}_signal:{note}")
        seq_tokens.append(_latency_bucket(int(ev.get("latency_ms", 0))))  # A

    if seq_tokens:
        parts.append("seq " + " ".join(seq_tokens))
    if transitions:
        parts.append("transitions " + " ".join(transitions))

    # v100: absence tokens DISABLED (latency-only variant)
    _ = activated  # silence linter

    parts.append(f"outcome:{trace['outcome']}")
    parts.append(f"outcome_group:{derive_outcome_group(trace['outcome'])}")

    return " | ".join(parts)


# -----------------------------------------------------------------------------
# 2-4. Embedding, reduction, clustering
# -----------------------------------------------------------------------------


def embed_documents(docs: list[str]) -> np.ndarray:
    model = SentenceTransformer(EMBED_MODEL_NAME)
    embs = model.encode(
        docs,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=False,
    )
    return embs.astype(np.float32)


def reduce_umap(embs: np.ndarray) -> np.ndarray:
    reducer = umap.UMAP(**UMAP_PARAMS)
    return reducer.fit_transform(embs)


def cluster_hdbscan(coords: np.ndarray) -> np.ndarray:
    clusterer = hdbscan.HDBSCAN(**HDBSCAN_PARAMS)
    return clusterer.fit_predict(coords)


# -----------------------------------------------------------------------------
# 5. c-TF-IDF cluster labelling
# -----------------------------------------------------------------------------


def c_tfidf_labels(
    docs: list[str], cluster_ids: np.ndarray, top_n: int = TOP_N_TERMS
) -> dict[int, list[str]]:
    """Class-based TF-IDF: concatenate docs per cluster, compute relative
    term frequency, weight by log((1+N)/(1+df)) where df counts clusters
    containing the term (source-claims §6.5.1)."""
    cluster_docs: dict[int, list[str]] = defaultdict(list)
    for d, c in zip(docs, cluster_ids):
        cluster_docs[int(c)].append(d)

    clusters = sorted(cluster_docs.keys())
    joined = [" ".join(cluster_docs[c]) for c in clusters]

    vec = CountVectorizer(
        token_pattern=r"(?u)[A-Za-z_][\w:/\->=,]*",
        lowercase=True,
        min_df=1,
    )
    X = vec.fit_transform(joined)
    vocab = np.array(vec.get_feature_names_out())

    tf = np.asarray(X.todense(), dtype=np.float64)
    row_sums = tf.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    tf_norm = tf / row_sums

    N = len(clusters)
    df = (tf > 0).sum(axis=0)
    idf = np.log((1.0 + N) / (1.0 + df))
    scores = tf_norm * idf

    labels: dict[int, list[str]] = {}
    for i, c in enumerate(clusters):
        top_idx = np.argsort(scores[i])[::-1][:top_n]
        labels[c] = [str(vocab[j]) for j in top_idx if scores[i, j] > 0]
    return labels


# -----------------------------------------------------------------------------
# 6. Impact scoring (source-claims §5.5.1 / §6.8.1)
# -----------------------------------------------------------------------------


def compute_cluster_impact(
    cluster_ids: np.ndarray, severities: list[str]
) -> dict[int, dict]:
    total = len(cluster_ids)
    per_cluster: dict[int, dict] = {}
    df = pd.DataFrame({"cluster": cluster_ids, "severity": severities})
    for c, g in df.groupby("cluster"):
        size = len(g)
        sev_counts = g["severity"].value_counts().to_dict()
        mean_sev = (
            sum(SEVERITY_WEIGHTS.get(s, 0.0) for s in g["severity"]) / size
        )
        prevalence = size / total
        per_cluster[int(c)] = dict(
            size=int(size),
            prevalence=float(prevalence),
            severity_distribution={k: int(v) for k, v in sev_counts.items()},
            mean_severity_weight=float(mean_sev),
            severity_weighted_prevalence=float(prevalence * mean_sev),
            impact_score=float(prevalence * (prevalence * mean_sev)),
        )
    return per_cluster


# -----------------------------------------------------------------------------
# 7. Lift = P(cluster | case_type) / P(cluster)
# -----------------------------------------------------------------------------


def compute_lift(
    cluster_ids: np.ndarray, case_types: list[str]
) -> pd.DataFrame:
    df = pd.DataFrame({"cluster": cluster_ids, "case_type": case_types})
    total = len(df)
    cluster_p = df["cluster"].value_counts() / total
    rows = []
    for (c, ct), sub in df.groupby(["cluster", "case_type"]):
        case_total = (df["case_type"] == ct).sum()
        p_c_given_ct = len(sub) / case_total if case_total else 0.0
        p_c = cluster_p.get(c, 0.0)
        lift = (p_c_given_ct / p_c) if p_c > 0 else 0.0
        rows.append(
            dict(
                cluster=int(c),
                case_type=ct,
                count=int(len(sub)),
                p_cluster_given_case=float(p_c_given_ct),
                p_cluster=float(p_c),
                lift=float(lift),
            )
        )
    return pd.DataFrame(rows).sort_values(["cluster", "case_type"])


# -----------------------------------------------------------------------------
# 8. Backward suspect walk (source-claims §8)
# -----------------------------------------------------------------------------


def _find_focus_idx(events: list[dict], outcome: str) -> int | None:
    """Anchor selection (source-claims §8.3.1). First 'failure' event, else
    first 'signal' event, else last event when outcome != completed."""
    for i, ev in enumerate(events):
        if ev.get("type") == "failure":
            return i
        if ev.get("type") == "signal":
            return i
    if outcome in ("blocked", "failed", "review"):
        return len(events) - 1
    return None


def backward_walk_suspects(
    cluster_ids: np.ndarray, trace_rows: list[dict]
) -> pd.DataFrame:
    """Per-cluster aggregated suspect scores. Walks back up to WALK_DEPTH
    events from the focus event and scores agents by
    0.4*proximity + 0.3*frequency + 0.2*graph_connectivity + 0.1*role."""
    cluster_to_traces: dict[int, list[dict]] = defaultdict(list)
    for c, t in zip(cluster_ids, trace_rows):
        cluster_to_traces[int(c)].append(t)

    rows = []
    for c, traces in cluster_to_traces.items():
        prox_sum: Counter = Counter()
        freq_sum: Counter = Counter()
        bridge_sum: Counter = Counter()
        hits: Counter = Counter()
        n_traces_with_focus = 0

        for trace in traces:
            events = _strip_underscore_fields(trace["events"])
            focus_idx = _find_focus_idx(events, trace["outcome"])
            if focus_idx is None:
                continue
            n_traces_with_focus += 1
            start = max(0, focus_idx - WALK_DEPTH + 1)
            window = events[start : focus_idx + 1]
            wsize = max(1, len(window))

            adj: dict[str, set] = defaultdict(set)
            for ev in window:
                a = ev.get("agent", "?")
                to = ev.get("to")
                if to and to != a:
                    adj[a].add(to)
                    adj[to].add(a)

            agent_positions: dict[str, list[int]] = defaultdict(list)
            for offset, ev in enumerate(window):
                agent_positions[ev.get("agent", "?")].append(offset)

            for agent, positions in agent_positions.items():
                dists = [(wsize - 1) - p for p in positions]
                prox = max(1.0 / (1.0 + d) for d in dists)
                freq = len(positions) / wsize
                bridge = min(1.0, len(adj.get(agent, set())) / 6.0)

                prox_sum[agent] += prox
                freq_sum[agent] += freq
                bridge_sum[agent] += bridge
                hits[agent] += 1

        if n_traces_with_focus == 0:
            continue

        for agent, h in hits.items():
            prox = prox_sum[agent] / h
            freq = freq_sum[agent] / h
            bridge = bridge_sum[agent] / h
            role = ROLE_RELEVANCE[agent]
            score = (
                SUSPECT_WEIGHTS["proximity"] * prox
                + SUSPECT_WEIGHTS["frequency"] * freq
                + SUSPECT_WEIGHTS["bridge"] * bridge
                + SUSPECT_WEIGHTS["role"] * role
            )
            rows.append(
                dict(
                    cluster=c,
                    agent=agent,
                    n_traces_with_agent=int(h),
                    n_traces_with_focus=int(n_traces_with_focus),
                    proximity=float(prox),
                    frequency=float(freq),
                    graph_connectivity=float(bridge),
                    role_relevance=float(role),
                    suspect_score=float(score),
                )
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            ["cluster", "suspect_score"], ascending=[True, False]
        )
    return df


# -----------------------------------------------------------------------------
# Extension C: CUSUM drift detector (separate module; H3)
# -----------------------------------------------------------------------------
# Watches the OBSERVABLE price_usd field returned by the pricing agent. We
# never read _raw_price_usd (it would be cheating; see README "Conflict with
# hypotheses.md"). Per cluster of sufficient size, bucket pricing returns by
# `bucket_days` and CUSUM on (bucket_mean - ref_mean)/ref_mean, where ref_mean
# is the cluster's pre-`ref_days` baseline and slack k = 1 std of normalized
# reference bucket means (data-driven, no hidden ground truth).


def cusum_drift(
    raw_traces: list[dict],
    cluster_ids: np.ndarray,
    bucket_days: int = 5,
    h: float = 0.004,
    ref_days: int = 45,
    min_cluster: int = 100,
) -> pd.DataFrame:
    """CUSUM is applied to groupings where pricing-event-per-bucket is large
    enough for the signal-to-noise ratio to clear +0.4% drift: HDBSCAN
    clusters at or above `min_cluster`, plus per-case_type strata (which are
    larger and pricing-uniform). Case_type strata appear with cluster_id
    encoded as f'case:{name}'."""
    rows = []
    by_c: dict = defaultdict(list)
    for t, c in zip(raw_traces, cluster_ids):
        by_c[int(c)].append(t)
        by_c[f"case:{t['case_type']}"].append(t)
    for cid, ts in by_c.items():
        if cid == -1 or len(ts) < min_cluster:
            continue
        buckets: dict[int, list[float]] = defaultdict(list)
        for t in ts:
            b = (t["day"] // bucket_days) * bucket_days
            for ev in t["events"]:
                if ev.get("agent") == "pricing" and ev.get("type") == "return":
                    v = ev.get("value") or {}
                    p = v.get("price_usd")  # OBSERVABLE only
                    if p is not None:
                        buckets[b].append(float(p))
        days = sorted(buckets)
        if len(days) < 6:
            continue
        means = {d: float(np.mean(buckets[d])) for d in days}
        ref_days_list = [d for d in days if d < ref_days]
        post_days_list = [d for d in days if d >= ref_days]
        if len(ref_days_list) < 3 or len(post_days_list) < 3:
            continue
        ref_vals = np.array([means[d] for d in ref_days_list])
        ref = float(ref_vals.mean())
        if ref <= 0:
            continue
        # slack = 1 sigma of normalized reference bucket means (data-driven)
        k = float(ref_vals.std() / ref)
        S = 0.0
        alerted = False
        for d in post_days_list:
            dev = (means[d] - ref) / ref
            S = max(0.0, S + dev - k)
            if S > h and not alerted:
                rows.append(dict(
                    cluster_id=cid if isinstance(cid, str) else int(cid),
                    signal_name="price_usd_mean",
                    alert_day=int(d),
                    cumulative_deviation=round(S, 6),
                    threshold_crossed=h,
                ))
                alerted = True
    return pd.DataFrame(rows, columns=[
        "cluster_id","signal_name","alert_day","cumulative_deviation","threshold_crossed",
    ])


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------


def load_traces(path: Path) -> list[dict]:
    traces = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            # Strip ground truth from the in-memory pipeline copy.
            # The confusion matrix re-reads the file separately.
            t.pop("failure_modes", None)
            traces.append(t)
    return traces


def main() -> None:
    t0 = time.time()
    print(f"[baseline] loading traces from {TRACES_PATH}")
    traces = load_traces(TRACES_PATH)
    print(f"[baseline] loaded {len(traces)} traces")

    print("[baseline] building documents")
    docs = [build_document(t) for t in traces]
    case_types = [t["case_type"] for t in traces]
    severities = [derive_severity_label(t) for t in traces]

    print(f"[baseline] embedding (model={EMBED_MODEL_NAME})")
    t_e = time.time()
    embs = embed_documents(docs)
    print(f"  -> shape={embs.shape} in {time.time()-t_e:.1f}s")

    print("[baseline] UMAP")
    t_u = time.time()
    coords = reduce_umap(embs)
    print(f"  -> shape={coords.shape} in {time.time()-t_u:.1f}s")

    print("[baseline] HDBSCAN")
    t_c = time.time()
    cluster_ids = cluster_hdbscan(coords)
    print(f"  -> done in {time.time()-t_c:.1f}s")

    n_noise = int((cluster_ids == -1).sum())
    n_clusters = int(len({c for c in cluster_ids if c != -1}))
    print(
        f"[baseline] n_clusters={n_clusters} noise={n_noise} "
        f"({100*n_noise/len(cluster_ids):.1f}% of {len(cluster_ids)})"
    )

    print("[baseline] c-TF-IDF labels")
    labels = c_tfidf_labels(docs, cluster_ids, top_n=TOP_N_TERMS)

    impact = compute_cluster_impact(cluster_ids, severities)
    print("[baseline] lift")
    lift_df = compute_lift(cluster_ids, case_types)

    print("[baseline] suspect walk on high-impact clusters")
    nonnoise = [c for c in impact if c != -1]
    if nonnoise:
        med = float(np.median([impact[c]["impact_score"] for c in nonnoise]))
        high_impact = {c for c in nonnoise if impact[c]["impact_score"] >= med}
    else:
        high_impact = set()
    walk_mask = np.array([c in high_impact for c in cluster_ids], dtype=bool)
    suspects_df = backward_walk_suspects(
        cluster_ids[walk_mask],
        [traces[i] for i in range(len(traces)) if walk_mask[i]],
    )

    # -- write outputs --------------------------------------------------------

    clusters_path = OUT_DIR / "clusters.jsonl"
    with clusters_path.open("w") as f:
        for i, t in enumerate(traces):
            f.write(
                json.dumps(
                    dict(
                        trace_id=t["trace_id"],
                        cluster_id=int(cluster_ids[i]),
                        document=docs[i],
                        umap_coords=[float(x) for x in coords[i]],
                    )
                )
                + "\n"
            )
    print(f"[baseline] wrote {clusters_path}")

    cluster_labels_obj = {}
    for c, info in impact.items():
        cluster_labels_obj[str(c)] = dict(
            top_terms=labels.get(c, []),
            size=info["size"],
            prevalence=info["prevalence"],
            severity_distribution=info["severity_distribution"],
            mean_severity_weight=info["mean_severity_weight"],
            severity_weighted_prevalence=info[
                "severity_weighted_prevalence"
            ],
            impact_score=info["impact_score"],
            high_impact=bool(c in high_impact),
        )
    labels_path = OUT_DIR / "cluster_labels.json"
    labels_path.write_text(json.dumps(cluster_labels_obj, indent=2))
    print(f"[baseline] wrote {labels_path}")

    # cluster_x_failure_mode.csv -- the Statistician's primary input.
    # We re-read ground-truth labels ONLY here to emit the confusion
    # matrix; the pipeline itself never consumed failure_modes.
    raw = []
    with TRACES_PATH.open() as f:
        for line in f:
            if line.strip():
                raw.append(json.loads(line))
    fm_lists = [r.get("failure_modes", []) or [] for r in raw]

    all_modes = [
        "substitution_reroute",
        "compliance_skipped_under_tariff",
        "stale_quote_slow_pricing",
        "pricing_drift",
        "escalation_loop",
        "random_noise_failure",
        "clean",
    ]
    cluster_set = sorted(set(int(c) for c in cluster_ids))
    counts: dict[int, Counter] = {c: Counter() for c in cluster_set}
    for c, modes in zip(cluster_ids, fm_lists):
        if not modes:
            counts[int(c)]["clean"] += 1
        else:
            for m in modes:
                counts[int(c)][m] += 1
    conf_rows = []
    for c in cluster_set:
        row = {"cluster": c, "cluster_size": int((cluster_ids == c).sum())}
        for m in all_modes:
            row[m] = counts[c].get(m, 0)
        conf_rows.append(row)
    conf_df = pd.DataFrame(conf_rows)
    conf_path = OUT_DIR / "cluster_x_failure_mode.csv"
    conf_df.to_csv(conf_path, index=False)
    print(f"[baseline] wrote {conf_path}")

    lift_path = OUT_DIR / "lift.csv"
    lift_df.to_csv(lift_path, index=False)
    print(f"[baseline] wrote {lift_path}")

    susp_path = OUT_DIR / "suspects.csv"
    suspects_df.to_csv(susp_path, index=False)
    print(f"[baseline] wrote {susp_path}")

    print("[improved] CUSUM drift detector (Extension C)")
    drift_df = cusum_drift(traces, cluster_ids)
    drift_path = OUT_DIR / "drift_alerts.csv"
    drift_df.to_csv(drift_path, index=False)
    print(f"[improved] wrote {drift_path} ({len(drift_df)} alerts)")

    runtime = time.time() - t0
    meta = dict(
        seed=SEED,
        n_traces=len(traces),
        n_clusters=n_clusters,
        n_noise=n_noise,
        embed_model=EMBED_MODEL_NAME,
        embedding_dim=int(embs.shape[1]),
        umap=UMAP_PARAMS,
        hdbscan=HDBSCAN_PARAMS,
        top_n_terms=TOP_N_TERMS,
        severity_weights=SEVERITY_WEIGHTS,
        suspect_weights=SUSPECT_WEIGHTS,
        walk_depth=WALK_DEPTH,
        library_versions=dict(
            python=platform.python_version(),
            numpy=np.__version__,
            pandas=pd.__version__,
            sklearn=sklearn.__version__,
            umap_learn=umap.__version__,
            sentence_transformers=__import__(
                "sentence_transformers"
            ).__version__,
            hdbscan=getattr(hdbscan, "__version__", "unknown"),
        ),
        runtime_seconds=runtime,
        platform=platform.platform(),
        variant="improved",
    )
    meta_path = OUT_DIR / "run_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, default=str))
    print(f"[baseline] wrote {meta_path}")

    print(
        f"[baseline] DONE in {runtime:.1f}s -- "
        f"{n_clusters} clusters, {n_noise} noise"
    )


if __name__ == "__main__":
    main()
