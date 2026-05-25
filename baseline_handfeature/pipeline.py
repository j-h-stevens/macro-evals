"""
Hand-feature baseline for trace clustering.

Motivation (Carmack, panel critique C5): the cookbook's pipeline runs
MiniLM -> UMAP -> HDBSCAN -> c-TF-IDF on serialized trace documents. If a
trivial ~20-dim feature vector hand-built from the same trace JSON
matches or beats that pipeline on the six pre-registered failure modes,
the cookbook's machinery is auditing decoration. This module strips the
framing and asks the question directly.

Features (15-25 dims):
  - case_type one-hot                          (5 dims)
  - outcome one-hot (completed/review/blocked/failed)  (4 dims)
  - did_compliance_fire                        (1 dim)
  - n_distinct_agents normalized by 7          (1 dim)
  - log_event_count                            (1 dim)
  - max_latency_ms / 1000, clipped at 10       (1 dim)
  - has_loop (any (caller,callee) edge repeats >=2)  (1 dim)
  - top-K agent-bigram counts, normalized      (K = 8, 8 dims)

Clustering: sklearn.cluster.KMeans, n_clusters matched to the improved
HDBSCAN output (121, read from improved/outputs/cluster_labels.json),
random_state=42.

Outputs:
  - baseline_handfeature/outputs/cluster_x_failure_mode.csv
  - baseline_handfeature/outputs/run_metadata.json
  - baseline_handfeature/outputs/clusters.jsonl (trace_id -> cluster_id)

NB: ground-truth labels (failure_modes, underscore-prefixed fields) are
stripped from the in-memory copy used to build features. The confusion
matrix re-reads the raw file separately, matching the convention used
by baseline/pipeline.py and improved/pipeline.py.
"""

from __future__ import annotations

import json
import math
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

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
os.environ.setdefault("PYTHONHASHSEED", str(SEED))

import sklearn  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
TRACES_PATH = PROJECT / "sim" / "data" / "traces.jsonl"
IMPROVED_LABELS = PROJECT / "improved" / "outputs" / "cluster_labels.json"
OUT_DIR = ROOT / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CASE_TYPES = [
    "standard_build",
    "supplier_substitution",
    "regulated_export",
    "expedited_delivery",
    "custom_configuration",
]
OUTCOMES = ["completed", "review", "blocked", "failed"]
KNOWN_AGENTS = [
    "orchestrator",
    "pricing",
    "supply",
    "compliance",
    "scheduling",
    "release",
    "factory",
]
TOP_K_BIGRAMS = 8

ALL_MODES = [
    "substitution_reroute",
    "compliance_skipped_under_tariff",
    "stale_quote_slow_pricing",
    "pricing_drift",
    "escalation_loop",
    "random_noise_failure",
    "clean",
]

UNDERSCORE_KEY_RE = re.compile(r"^_")


def _strip_underscore_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_underscore_fields(v)
            for k, v in obj.items()
            if not UNDERSCORE_KEY_RE.match(k)
        }
    if isinstance(obj, list):
        return [_strip_underscore_fields(v) for v in obj]
    return obj


def load_traces(path: Path) -> list[dict]:
    traces = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            t.pop("failure_modes", None)
            t["events"] = _strip_underscore_fields(t["events"])
            traces.append(t)
    return traces


def agent_edges(events: list[dict]) -> list[tuple[str, str]]:
    """Pairs of (caller_agent, callee_agent) for call/handoff events."""
    edges = []
    for ev in events:
        etype = ev.get("type")
        if etype in ("call", "handoff"):
            a = ev.get("agent")
            to = ev.get("to")
            if a and to:
                edges.append((a, to))
    return edges


def compute_top_bigrams(traces: list[dict], k: int) -> list[tuple[str, str]]:
    c: Counter = Counter()
    for t in traces:
        for e in agent_edges(t["events"]):
            c[e] += 1
    return [bg for bg, _ in c.most_common(k)]


def featurize(
    trace: dict, top_bigrams: list[tuple[str, str]]
) -> np.ndarray:
    events = trace["events"]

    # case_type one-hot
    ct = np.zeros(len(CASE_TYPES), dtype=np.float32)
    if trace["case_type"] in CASE_TYPES:
        ct[CASE_TYPES.index(trace["case_type"])] = 1.0

    # outcome one-hot
    oc = np.zeros(len(OUTCOMES), dtype=np.float32)
    if trace["outcome"] in OUTCOMES:
        oc[OUTCOMES.index(trace["outcome"])] = 1.0

    # did_compliance_fire
    did_compliance = float(any(ev.get("agent") == "compliance" for ev in events))

    # n_distinct_agents / 7
    distinct = {ev.get("agent") for ev in events if ev.get("agent")}
    n_dist = len(distinct) / 7.0

    # log_event_count
    log_n = math.log1p(len(events))

    # max_latency_ms / 1000, clipped at 10
    max_lat = max((int(ev.get("latency_ms", 0)) for ev in events), default=0)
    max_lat_feat = min(max_lat / 1000.0, 10.0)

    # has_loop: any (caller, callee) edge repeats >= 2 times
    edge_counts = Counter(agent_edges(events))
    has_loop = float(any(v >= 2 for v in edge_counts.values()))

    # agent-bigram top-K, normalized by total bigram count in the trace
    total = sum(edge_counts.values()) or 1
    bg = np.zeros(len(top_bigrams), dtype=np.float32)
    for i, b in enumerate(top_bigrams):
        bg[i] = edge_counts.get(b, 0) / total

    scalar = np.array(
        [did_compliance, n_dist, log_n, max_lat_feat, has_loop],
        dtype=np.float32,
    )
    return np.concatenate([ct, oc, scalar, bg]).astype(np.float32)


def read_n_clusters(path: Path) -> int:
    d = json.loads(path.read_text())
    non_noise = [int(k) for k in d.keys() if int(k) != -1]
    return len(non_noise)


def main() -> None:
    t0 = time.time()
    print(f"[handfeature] loading traces from {TRACES_PATH}")
    traces = load_traces(TRACES_PATH)
    print(f"[handfeature] loaded {len(traces)} traces")

    top_bigrams = compute_top_bigrams(traces, TOP_K_BIGRAMS)
    print(f"[handfeature] top-{TOP_K_BIGRAMS} bigrams: {top_bigrams}")

    X = np.stack([featurize(t, top_bigrams) for t in traces])
    print(f"[handfeature] feature matrix shape={X.shape}")

    n_clusters = read_n_clusters(IMPROVED_LABELS)
    print(f"[handfeature] n_clusters={n_clusters} (matched to improved)")

    km = KMeans(n_clusters=n_clusters, random_state=SEED, n_init=10)
    cluster_ids = km.fit_predict(X)

    # write clusters.jsonl
    cl_path = OUT_DIR / "clusters.jsonl"
    with cl_path.open("w") as f:
        for t, c in zip(traces, cluster_ids):
            f.write(
                json.dumps(dict(trace_id=t["trace_id"], cluster_id=int(c)))
                + "\n"
            )
    print(f"[handfeature] wrote {cl_path}")

    # Build confusion matrix by re-reading raw file for ground truth.
    raw = []
    with TRACES_PATH.open() as f:
        for line in f:
            if line.strip():
                raw.append(json.loads(line))
    fm_lists = [r.get("failure_modes", []) or [] for r in raw]

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
        for m in ALL_MODES:
            row[m] = counts[c].get(m, 0)
        conf_rows.append(row)
    conf_df = pd.DataFrame(conf_rows)
    conf_path = OUT_DIR / "cluster_x_failure_mode.csv"
    conf_df.to_csv(conf_path, index=False)
    print(f"[handfeature] wrote {conf_path}")

    # Per-mode recall@cluster summary (majority-cluster heuristic).
    summary = {}
    by_mode: dict[str, list[int]] = defaultdict(list)
    for c, modes in zip(cluster_ids, fm_lists):
        for m in modes:
            by_mode[m].append(int(c))
    for mode in ALL_MODES:
        if mode == "clean":
            continue
        cids = by_mode.get(mode, [])
        if not cids:
            summary[mode] = dict(n=0, majority_cluster=None, recall=0.0)
            continue
        cnt = Counter(cids)
        mc, _ = cnt.most_common(1)[0]
        recall = cnt[mc] / len(cids)
        summary[mode] = dict(
            n=len(cids), majority_cluster=int(mc), recall=float(recall)
        )
    print(f"[handfeature] per-mode recall@cluster: {summary}")

    runtime = time.time() - t0
    meta = dict(
        seed=SEED,
        n_traces=len(traces),
        n_clusters=n_clusters,
        feature_dim=int(X.shape[1]),
        top_bigrams=[list(b) for b in top_bigrams],
        per_mode_recall=summary,
        clustering="sklearn.cluster.KMeans(n_init=10)",
        library_versions=dict(
            python=platform.python_version(),
            numpy=np.__version__,
            pandas=pd.__version__,
            sklearn=sklearn.__version__,
        ),
        runtime_seconds=runtime,
        platform=platform.platform(),
        variant="handfeature_baseline",
    )
    meta_path = OUT_DIR / "run_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, default=str))
    print(f"[handfeature] wrote {meta_path}")
    print(f"[handfeature] DONE in {runtime:.1f}s")


if __name__ == "__main__":
    main()
