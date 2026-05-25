"""
Held-out validation (80/20 split) for the macro-evals article.

The article's bootstrap CIs hold cluster identity fixed and resample
per-trace indicators. That captures sampling variability inside the
training set; it does not establish that the clusters generalize. This
module:

  1. Partitions the 5,000 traces 80/20 by hash(trace_id) % 5 (== 0 -> held-out).
  2. Re-runs the BASELINE pipeline (build_document + MiniLM + UMAP + HDBSCAN)
     on the 80% train set with seed 42 and identical hyperparameters.
  3. Re-runs the IMPROVED pipeline (latency + absent tokens + MiniLM + UMAP +
     HDBSCAN) on the 80% train set with the same settings.
  4. For each held-out trace: embeds via the same MiniLM model used in
     training, transforms via the trained UMAP, and assigns a cluster via
     hdbscan.approximate_predict against the trained HDBSCAN model.
  5. Re-derives recall@cluster per failure mode on the 20% held-out set
     using the majority-cluster mapping fit on the 80% TRAIN set (this is
     the held-out evaluation; out-of-sample cluster identity).
  6. Recomputes E5 (backward walk vs MFA-5) on the held-out structural
     traces, using the baseline-train suspect table for the walk.

Writes: eval/held_out_results.md and eval/held_out_raw.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
os.environ.setdefault("PYTHONHASHSEED", str(SEED))

# import the actual pipeline modules so we share document construction
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hdbscan  # noqa: E402
import umap  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from baseline.pipeline import build_document as build_baseline_doc  # noqa: E402
from improved.pipeline import build_document as build_improved_doc  # noqa: E402

TRACES_PATH = ROOT / "sim" / "data" / "traces.jsonl"
OUT_MD = ROOT / "eval" / "held_out_results.md"
OUT_JSON = ROOT / "eval" / "held_out_raw.json"

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

UMAP_PARAMS = dict(
    n_neighbors=15, n_components=5, min_dist=0.0,
    metric="cosine", random_state=SEED,
)
HDBSCAN_PARAMS = dict(min_cluster_size=20, min_samples=5, metric="euclidean")

FAILURE_MODES = [
    "substitution_reroute",
    "compliance_skipped_under_tariff",
    "stale_quote_slow_pricing",
    "pricing_drift",
    "escalation_loop",
    "random_noise_failure",
]

GT_AGENT_STRICT = {
    "substitution_reroute": {"supply"},
    "escalation_loop": {"compliance"},
}
GT_AGENT_LENIENT = {
    "substitution_reroute": {"supply"},
    "escalation_loop": {"compliance", "release"},
}


# ---------- Determinism: split traces ----------

def held_out_mask(trace_ids: list[str]) -> np.ndarray:
    """Deterministic 80/20 split by hash(trace_id) % 5 == 0 (held-out)."""
    out = np.zeros(len(trace_ids), dtype=bool)
    for i, tid in enumerate(trace_ids):
        h = int(hashlib.md5(tid.encode()).hexdigest(), 16)
        out[i] = (h % 5 == 0)
    return out


# ---------- Pipeline helpers ----------

def load_traces() -> list[dict]:
    out = []
    with TRACES_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def embed(docs: list[str], model: SentenceTransformer) -> np.ndarray:
    embs = model.encode(
        docs, batch_size=64, show_progress_bar=False,
        convert_to_numpy=True, normalize_embeddings=False,
    )
    return embs.astype(np.float32)


def run_pipeline(
    train_traces: list[dict],
    test_traces: list[dict],
    build_doc,
    tag: str,
) -> dict:
    """Returns dict with train_cluster_ids, test_cluster_ids."""
    print(f"[{tag}] building documents (train={len(train_traces)}, test={len(test_traces)})")
    train_docs = [build_doc(t) for t in train_traces]
    test_docs = [build_doc(t) for t in test_traces]

    print(f"[{tag}] embedding (model={EMBED_MODEL_NAME})")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    train_embs = embed(train_docs, model)
    test_embs = embed(test_docs, model)

    print(f"[{tag}] UMAP fit on train")
    reducer = umap.UMAP(**UMAP_PARAMS)
    train_coords = reducer.fit_transform(train_embs)
    test_coords = reducer.transform(test_embs)

    print(f"[{tag}] HDBSCAN fit on train")
    clusterer = hdbscan.HDBSCAN(prediction_data=True, **HDBSCAN_PARAMS)
    train_labels = clusterer.fit_predict(train_coords)

    print(f"[{tag}] approximate_predict on held-out")
    test_labels, _ = hdbscan.approximate_predict(clusterer, test_coords)

    n_train_clusters = len({c for c in train_labels if c != -1})
    n_train_noise = int((train_labels == -1).sum())
    n_test_noise = int((test_labels == -1).sum())
    print(
        f"[{tag}] train: n_clusters={n_train_clusters} noise={n_train_noise} "
        f"({100*n_train_noise/len(train_labels):.1f}%); "
        f"test noise={n_test_noise} ({100*n_test_noise/len(test_labels):.1f}%)"
    )
    return dict(
        train_labels=train_labels,
        test_labels=test_labels,
        n_train_clusters=n_train_clusters,
        n_train_noise=n_train_noise,
        n_test_noise=n_test_noise,
    )


# ---------- Recall@cluster using train-fit majority cluster ----------

def majority_cluster_on_train(
    train_labels: np.ndarray, train_traces: list[dict], mode: str
) -> int | None:
    tids = [
        i for i, t in enumerate(train_traces)
        if mode in (t.get("failure_modes") or [])
    ]
    counts: Counter = Counter()
    for i in tids:
        c = int(train_labels[i])
        if c != -1:
            counts[c] += 1
    if not counts:
        return None
    max_count = max(counts.values())
    return min(c for c, n in counts.items() if n == max_count)


def recall_on_set(
    labels: np.ndarray, traces: list[dict], mode: str, majority_c: int
) -> tuple[float, int, int]:
    """Returns (recall, hits, n_traces_with_mode)."""
    tids = [
        i for i, t in enumerate(traces)
        if mode in (t.get("failure_modes") or [])
    ]
    if not tids:
        return 0.0, 0, 0
    hits = sum(1 for i in tids if int(labels[i]) == majority_c)
    return hits / len(tids), hits, len(tids)


# ---------- E5 helpers (MFA-5 and backward walk top-1) ----------

def pick_focus_idx(events: list[dict]) -> int:
    for i, e in enumerate(events):
        if e.get("type") == "signal":
            return i
    return len(events) - 1


def mfa_attribution(events: list[dict], focus_idx: int, n: int = 5) -> str:
    start = max(0, focus_idx - n + 1)
    window = events[start: focus_idx + 1]
    counts = Counter(e["agent"] for e in window)
    if not counts:
        return "unknown"
    max_count = max(counts.values())
    for e in reversed(window):
        if counts[e["agent"]] == max_count:
            return e["agent"]
    return "unknown"


def build_suspect_top1(
    train_labels: np.ndarray, train_traces: list[dict]
) -> dict[int, str]:
    """Per-cluster top-1 suspect agent using the same scoring as
    baseline/pipeline.py: 0.4*proximity + 0.3*frequency + 0.2*bridge + 0.1*role."""
    SUSPECT_WEIGHTS = dict(proximity=0.4, frequency=0.3, bridge=0.2, role=0.1)
    ROLE = defaultdict(lambda: 1.0, {"orchestrator": 0.5})
    WALK_DEPTH = 10

    cluster_to_traces: dict[int, list[dict]] = defaultdict(list)
    for c, t in zip(train_labels, train_traces):
        cluster_to_traces[int(c)].append(t)

    out: dict[int, str] = {}
    for c, ts in cluster_to_traces.items():
        if c == -1:
            continue
        prox_sum: Counter = Counter()
        freq_sum: Counter = Counter()
        bridge_sum: Counter = Counter()
        hits: Counter = Counter()
        for trace in ts:
            events = trace["events"]
            # focus: first failure/signal else last if non-completed
            focus = None
            for i, ev in enumerate(events):
                if ev.get("type") == "failure":
                    focus = i; break
                if ev.get("type") == "signal":
                    focus = i; break
            if focus is None:
                if trace["outcome"] in ("blocked", "failed", "review"):
                    focus = len(events) - 1
                else:
                    continue
            start = max(0, focus - WALK_DEPTH + 1)
            window = events[start:focus + 1]
            wsize = max(1, len(window))
            adj: dict[str, set] = defaultdict(set)
            for ev in window:
                a = ev.get("agent", "?")
                to = ev.get("to")
                if to and to != a:
                    adj[a].add(to); adj[to].add(a)
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
        if not hits:
            continue
        best_score = -1.0; best_agent = None
        for agent, h in hits.items():
            prox = prox_sum[agent] / h
            freq = freq_sum[agent] / h
            bridge = bridge_sum[agent] / h
            role = ROLE[agent]
            score = (SUSPECT_WEIGHTS["proximity"] * prox
                     + SUSPECT_WEIGHTS["frequency"] * freq
                     + SUSPECT_WEIGHTS["bridge"] * bridge
                     + SUSPECT_WEIGHTS["role"] * role)
            if score > best_score:
                best_score = score; best_agent = agent
        if best_agent is not None:
            out[c] = best_agent
    return out


def bootstrap_mean(ind: np.ndarray, rng: np.random.Generator, n_boot: int = 1000):
    n = len(ind)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = float(ind.mean())
    idx = rng.integers(0, n, size=(n_boot, n))
    s = ind[idx].mean(axis=1)
    lo, hi = np.percentile(s, [2.5, 97.5])
    return point, float(lo), float(hi)


def bootstrap_paired(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n_boot: int = 1000):
    n = len(a)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = float(b.mean() - a.mean())
    idx = rng.integers(0, n, size=(n_boot, n))
    d = b[idx].mean(axis=1) - a[idx].mean(axis=1)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return point, float(lo), float(hi)


# ---------- main ----------

def main() -> None:
    t0 = time.time()
    traces = load_traces()
    trace_ids = [t["trace_id"] for t in traces]
    mask_test = held_out_mask(trace_ids)
    train_idx = np.where(~mask_test)[0]
    test_idx = np.where(mask_test)[0]
    train_traces = [traces[i] for i in train_idx]
    test_traces = [traces[i] for i in test_idx]
    print(f"split: train={len(train_traces)} test={len(test_traces)}")

    # Run baseline + improved on train; predict on held-out.
    res_base = run_pipeline(
        [{**t, "failure_modes": None} for t in train_traces],  # ground truth not used by build_doc
        [{**t, "failure_modes": None} for t in test_traces],
        build_baseline_doc,
        tag="baseline",
    )
    res_impr = run_pipeline(
        [{**t, "failure_modes": None} for t in train_traces],
        [{**t, "failure_modes": None} for t in test_traces],
        build_improved_doc,
        tag="improved",
    )

    # Per-mode recall using train-fit majority cluster, applied to BOTH train (in-sample)
    # and held-out (out-of-sample).
    rng = np.random.default_rng(SEED)
    per_mode: dict = {}
    for mode in FAILURE_MODES:
        mc_b = majority_cluster_on_train(res_base["train_labels"], train_traces, mode)
        mc_i = majority_cluster_on_train(res_impr["train_labels"], train_traces, mode)

        # in-sample on train
        b_train_r, b_train_h, b_train_n = (
            recall_on_set(res_base["train_labels"], train_traces, mode, mc_b)
            if mc_b is not None else (0.0, 0, 0)
        )
        i_train_r, i_train_h, i_train_n = (
            recall_on_set(res_impr["train_labels"], train_traces, mode, mc_i)
            if mc_i is not None else (0.0, 0, 0)
        )
        # held-out
        b_test_r, b_test_h, b_test_n = (
            recall_on_set(res_base["test_labels"], test_traces, mode, mc_b)
            if mc_b is not None else (0.0, 0, 0)
        )
        i_test_r, i_test_h, i_test_n = (
            recall_on_set(res_impr["test_labels"], test_traces, mode, mc_i)
            if mc_i is not None else (0.0, 0, 0)
        )
        per_mode[mode] = dict(
            baseline=dict(
                majority_cluster_on_train=mc_b,
                in_sample_recall=b_train_r, in_sample_n=b_train_n,
                held_out_recall=b_test_r, held_out_hits=b_test_h, held_out_n=b_test_n,
            ),
            improved=dict(
                majority_cluster_on_train=mc_i,
                in_sample_recall=i_train_r, in_sample_n=i_train_n,
                held_out_recall=i_test_r, held_out_hits=i_test_h, held_out_n=i_test_n,
            ),
        )

    # E2 reassessment: stale_quote_slow_pricing
    e2_mode = "stale_quote_slow_pricing"
    e2 = per_mode[e2_mode]
    e2_gap_train = e2["improved"]["in_sample_recall"] - e2["baseline"]["in_sample_recall"]
    e2_gap_test = e2["improved"]["held_out_recall"] - e2["baseline"]["held_out_recall"]

    # Paired bootstrap of held-out per-trace hit indicators for E2.
    mc_b = e2["baseline"]["majority_cluster_on_train"]
    mc_i = e2["improved"]["majority_cluster_on_train"]
    tids = [i for i, t in enumerate(test_traces) if e2_mode in (t.get("failure_modes") or [])]
    if tids and mc_b is not None and mc_i is not None:
        ind_b = np.array([1 if int(res_base["test_labels"][i]) == mc_b else 0 for i in tids])
        ind_i = np.array([1 if int(res_impr["test_labels"][i]) == mc_i else 0 for i in tids])
        e2_gap_p, e2_gap_lo, e2_gap_hi = bootstrap_paired(
            ind_b, ind_i, np.random.default_rng(SEED + 2)
        )
    else:
        e2_gap_p = e2_gap_test; e2_gap_lo = e2_gap_hi = 0.0

    # E2 in-sample verdict: same thresholds as the original article.
    e2_in_supports = (e2_gap_train > 0.50) and (e2["baseline"]["in_sample_recall"] < 0.20) \
        and (e2["improved"]["in_sample_recall"] >= 0.70)
    e2_in_refutes = (e2["baseline"]["in_sample_recall"] >= 0.35) or (e2_gap_train <= 0)

    # E2 held-out verdict using gap CI lower bound
    e2_held_supports = (e2_gap_lo > 0.50) and (e2["baseline"]["held_out_recall"] < 0.20) \
        and (e2["improved"]["held_out_recall"] >= 0.70)
    e2_held_refutes = (e2["baseline"]["held_out_recall"] >= 0.35) or (e2_gap_lo <= 0)

    if e2_in_supports:
        e2_in_verdict = "MAGNITUDE SUPPORTED"
    elif e2_gap_train > 0 and not e2_in_refutes:
        e2_in_verdict = "DIRECTION CONFIRMED"
    else:
        e2_in_verdict = "REFUTED"
    if e2_held_supports:
        e2_held_verdict = "MAGNITUDE SUPPORTED"
    elif e2_gap_p > 0 and not e2_held_refutes:
        e2_held_verdict = "DIRECTION CONFIRMED"
    else:
        e2_held_verdict = "REFUTED"

    # E5: backward walk vs MFA-5 on held-out structural traces.
    bw_top1_train = build_suspect_top1(res_base["train_labels"], train_traces)
    structural_test_idx = [
        i for i, t in enumerate(test_traces)
        if any(m in (t.get("failure_modes") or []) for m in ("substitution_reroute", "escalation_loop"))
    ]
    mfa_pred = []
    bw_pred = []
    gt_strict = []
    gt_lenient = []
    per_mode_e5_test = {"substitution_reroute": {"n": 0, "mfa_hits": 0, "bw_hits": 0},
                        "escalation_loop": {"n": 0, "mfa_hits": 0, "bw_hits": 0}}
    for i in structural_test_idx:
        t = test_traces[i]
        modes = t.get("failure_modes") or []
        fi = pick_focus_idx(t["events"])
        mfa = mfa_attribution(t["events"], fi, n=5)
        c = int(res_base["test_labels"][i])
        bw = bw_top1_train.get(c, "unknown")
        mfa_pred.append(mfa); bw_pred.append(bw)
        # ground truth: union over the modes the trace has
        strict_set: set[str] = set(); lenient_set: set[str] = set()
        for m in modes:
            if m in GT_AGENT_STRICT:
                strict_set |= GT_AGENT_STRICT[m]; lenient_set |= GT_AGENT_LENIENT[m]
                per_mode_e5_test[m]["n"] += 1
                if mfa in GT_AGENT_STRICT[m]:
                    per_mode_e5_test[m]["mfa_hits"] += 1
                if bw in GT_AGENT_STRICT[m]:
                    per_mode_e5_test[m]["bw_hits"] += 1
        gt_strict.append(strict_set); gt_lenient.append(lenient_set)

    n_e5 = len(mfa_pred)
    if n_e5 > 0:
        mfa_s = np.array([1 if mfa_pred[i] in gt_strict[i] else 0 for i in range(n_e5)])
        bw_s = np.array([1 if bw_pred[i] in gt_strict[i] else 0 for i in range(n_e5)])
        mfa_l = np.array([1 if mfa_pred[i] in gt_lenient[i] else 0 for i in range(n_e5)])
        bw_l = np.array([1 if bw_pred[i] in gt_lenient[i] else 0 for i in range(n_e5)])
        mfa_s_p, mfa_s_lo, mfa_s_hi = bootstrap_mean(mfa_s, np.random.default_rng(SEED + 10))
        bw_s_p, bw_s_lo, bw_s_hi = bootstrap_mean(bw_s, np.random.default_rng(SEED + 11))
        gap_s_p, gap_s_lo, gap_s_hi = bootstrap_paired(mfa_s, bw_s, np.random.default_rng(SEED + 12))
        mfa_l_p, mfa_l_lo, mfa_l_hi = bootstrap_mean(mfa_l, np.random.default_rng(SEED + 13))
        bw_l_p, bw_l_lo, bw_l_hi = bootstrap_mean(bw_l, np.random.default_rng(SEED + 14))
        gap_l_p, gap_l_lo, gap_l_hi = bootstrap_paired(mfa_l, bw_l, np.random.default_rng(SEED + 15))
    else:
        mfa_s_p = bw_s_p = gap_s_p = 0.0
        mfa_s_lo = mfa_s_hi = bw_s_lo = bw_s_hi = gap_s_lo = gap_s_hi = 0.0
        mfa_l_p = bw_l_p = gap_l_p = mfa_l_lo = mfa_l_hi = bw_l_lo = bw_l_hi = gap_l_lo = gap_l_hi = 0.0

    e5_held = dict(
        n_structural_test=n_e5,
        strict=dict(
            mfa5_precision_at_1=mfa_s_p, mfa5_ci=(mfa_s_lo, mfa_s_hi),
            backward_walk_precision_at_1=bw_s_p, bw_ci=(bw_s_lo, bw_s_hi),
            gap_bw_minus_mfa5=gap_s_p, gap_ci=(gap_s_lo, gap_s_hi),
        ),
        lenient=dict(
            mfa5_precision_at_1=mfa_l_p, mfa5_ci=(mfa_l_lo, mfa_l_hi),
            backward_walk_precision_at_1=bw_l_p, bw_ci=(bw_l_lo, bw_l_hi),
            gap_bw_minus_mfa5=gap_l_p, gap_ci=(gap_l_lo, gap_l_hi),
        ),
        per_mode=per_mode_e5_test,
    )
    e5_held["verdict_strict"] = (
        "WALK BEATS MFA-5" if gap_s_p > 0 and gap_s_lo > 0
        else "MFA-5 BEATS WALK" if gap_s_p < 0 and gap_s_hi < 0
        else "NULL"
    )
    e5_held["verdict_lenient"] = (
        "WALK BEATS MFA-5" if gap_l_p > 0 and gap_l_lo > 0
        else "MFA-5 BEATS WALK" if gap_l_p < 0 and gap_l_hi < 0
        else "NULL"
    )

    runtime = time.time() - t0
    out_json = dict(
        seed=SEED,
        n_traces=len(traces),
        n_train=len(train_traces),
        n_test=len(test_traces),
        baseline_train_n_clusters=res_base["n_train_clusters"],
        baseline_train_noise=res_base["n_train_noise"],
        baseline_test_noise=res_base["n_test_noise"],
        improved_train_n_clusters=res_impr["n_train_clusters"],
        improved_train_noise=res_impr["n_train_noise"],
        improved_test_noise=res_impr["n_test_noise"],
        per_mode=per_mode,
        e2=dict(
            mode=e2_mode,
            in_sample_baseline=e2["baseline"]["in_sample_recall"],
            in_sample_improved=e2["improved"]["in_sample_recall"],
            in_sample_gap=e2_gap_train,
            in_sample_verdict=e2_in_verdict,
            held_out_baseline=e2["baseline"]["held_out_recall"],
            held_out_improved=e2["improved"]["held_out_recall"],
            held_out_gap=e2_gap_test,
            held_out_gap_ci=(e2_gap_lo, e2_gap_hi),
            held_out_verdict=e2_held_verdict,
        ),
        e5=e5_held,
        runtime_seconds=runtime,
    )
    OUT_JSON.write_text(json.dumps(out_json, indent=2, default=str))
    print(f"wrote {OUT_JSON}")

    # ----- Markdown report -----
    lines: list[str] = []
    lines.append("# Held-out validation (80/20 split)\n")
    lines.append(f"Seed {SEED}. Train: {len(train_traces)}; held-out: {len(test_traces)} "
                 f"(partition by `hash(trace_id) % 5 == 0`).\n")
    lines.append("Pipelines re-fit on train only. Held-out traces are embedded with the "
                 "same MiniLM model, projected with `UMAP.transform` against the train-fit "
                 "reducer, and assigned via `hdbscan.approximate_predict` against the "
                 "train-fit HDBSCAN. Majority cluster per failure mode is computed on the "
                 "TRAIN partition, then applied unchanged to the held-out set.\n")
    lines.append(f"Train cluster counts: baseline {res_base['n_train_clusters']} "
                 f"(noise {res_base['n_train_noise']}); improved {res_impr['n_train_clusters']} "
                 f"(noise {res_impr['n_train_noise']}).  "
                 f"Held-out noise (approximate_predict): baseline {res_base['n_test_noise']} / "
                 f"{len(test_traces)}; improved {res_impr['n_test_noise']} / {len(test_traces)}.\n")

    lines.append("## Per-mode recall@cluster: in-sample (train) vs held-out (test)\n")
    lines.append("| Mode | Baseline in-sample | Baseline held-out | Improved in-sample | Improved held-out |")
    lines.append("|---|---|---|---|---|")
    for mode in FAILURE_MODES:
        m = per_mode[mode]
        lines.append(
            f"| {mode} "
            f"| {m['baseline']['in_sample_recall']:.3f} (n={m['baseline']['in_sample_n']}) "
            f"| {m['baseline']['held_out_recall']:.3f} (n={m['baseline']['held_out_n']}) "
            f"| {m['improved']['in_sample_recall']:.3f} (n={m['improved']['in_sample_n']}) "
            f"| {m['improved']['held_out_recall']:.3f} (n={m['improved']['held_out_n']}) |"
        )
    lines.append("")

    lines.append("## E2 (H1 temporal, stale_quote_slow_pricing)\n")
    lines.append(f"- In-sample (train 80%): baseline {e2['baseline']['in_sample_recall']:.3f}, "
                 f"improved {e2['improved']['in_sample_recall']:.3f}, gap {e2_gap_train:+.3f}.")
    lines.append(f"- Held-out (test 20%): baseline {e2['baseline']['held_out_recall']:.3f}, "
                 f"improved {e2['improved']['held_out_recall']:.3f}, "
                 f"gap {e2_gap_test:+.3f} [{e2_gap_lo:+.3f}, {e2_gap_hi:+.3f}] "
                 f"(paired bootstrap on held-out hit indicators).")
    lines.append(f"- In-sample verdict: **{e2_in_verdict}**.  Held-out verdict: **{e2_held_verdict}**.\n")

    survives = (e2_in_verdict == e2_held_verdict)
    if survives:
        lines.append(f"The article's E2 verdict ('DIRECTION CONFIRMED') {'survives' if e2_held_verdict == 'DIRECTION CONFIRMED' else 'maps to ' + e2_held_verdict} on held-out data.\n")
    else:
        lines.append(f"E2's in-sample verdict ({e2_in_verdict}) does **not** survive held-out evaluation; held-out verdict is **{e2_held_verdict}**.\n")

    lines.append("## E5 (backward walk vs MFA-5 on held-out structural failures)\n")
    if n_e5 > 0:
        lines.append(f"- Held-out structural traces (substitution_reroute + escalation_loop): n={n_e5}.")
        lines.append("- Strict ground truth:")
        lines.append(f"  - MFA-5 precision@1: {mfa_s_p:.3f} [{mfa_s_lo:.3f}, {mfa_s_hi:.3f}]")
        lines.append(f"  - Backward walk precision@1: {bw_s_p:.3f} [{bw_s_lo:.3f}, {bw_s_hi:.3f}]")
        lines.append(f"  - Gap (walk - MFA-5): {gap_s_p:+.3f} [{gap_s_lo:+.3f}, {gap_s_hi:+.3f}]  "
                     f"=> **{e5_held['verdict_strict']}**")
        lines.append("- Lenient ground truth (escalation_loop GT = {compliance, release}):")
        lines.append(f"  - MFA-5 precision@1: {mfa_l_p:.3f} [{mfa_l_lo:.3f}, {mfa_l_hi:.3f}]")
        lines.append(f"  - Backward walk precision@1: {bw_l_p:.3f} [{bw_l_lo:.3f}, {bw_l_hi:.3f}]")
        lines.append(f"  - Gap (walk - MFA-5): {gap_l_p:+.3f} [{gap_l_lo:+.3f}, {gap_l_hi:+.3f}]  "
                     f"=> **{e5_held['verdict_lenient']}**")
        lines.append("")
        lines.append("Per-mode (strict, held-out):")
        for mode, d in per_mode_e5_test.items():
            mfa_r = d["mfa_hits"] / d["n"] if d["n"] else 0.0
            bw_r = d["bw_hits"] / d["n"] if d["n"] else 0.0
            lines.append(f"  - {mode}: n={d['n']}, MFA-5={mfa_r:.3f}, walk={bw_r:.3f}")
    else:
        lines.append("(No structural traces in held-out set; cannot evaluate.)")
    lines.append("")

    # Comparison to in-sample E5 in eval/raw_numbers.json
    raw_path = ROOT / "eval" / "raw_numbers.json"
    try:
        raw = json.loads(raw_path.read_text())
        is_gap = raw["E5"]["strict"]["gap_bw_minus_mfa5"]
        is_gap_lo = raw["E5"]["strict"]["gap_ci_lo"]
        is_gap_hi = raw["E5"]["strict"]["gap_ci_hi"]
        lines.append(f"In-sample comparison (from `eval/raw_numbers.json`): strict gap "
                     f"{is_gap:+.3f} [{is_gap_lo:+.3f}, {is_gap_hi:+.3f}]. The article's "
                     f"verdict is 'walk loses to MFA-5'. ")
        if e5_held["verdict_strict"] == "MFA-5 BEATS WALK":
            lines.append("**Held-out verdict matches in-sample: walk still loses to MFA-5.**")
        elif e5_held["verdict_strict"] == "WALK BEATS MFA-5":
            lines.append("**Held-out verdict REVERSES in-sample: walk now beats MFA-5 on held-out.**")
        else:
            lines.append("**Held-out verdict is NULL: the gap is no longer significant out of sample.**")
    except Exception:
        pass
    lines.append("")
    lines.append(f"_Runtime: {runtime:.1f}s. Written by `eval/held_out.py`._")
    OUT_MD.write_text("\n".join(lines))
    print(f"wrote {OUT_MD}")

    print("\n=== Held-out summary ===")
    print(f"E2 in-sample verdict: {e2_in_verdict}")
    print(f"E2 held-out verdict: {e2_held_verdict}")
    print(f"E5 strict held-out: {e5_held['verdict_strict']} (gap {gap_s_p:+.3f} [{gap_s_lo:+.3f}, {gap_s_hi:+.3f}])")
    print(f"E5 lenient held-out: {e5_held['verdict_lenient']} (gap {gap_l_p:+.3f} [{gap_l_lo:+.3f}, {gap_l_hi:+.3f}])")


if __name__ == "__main__":
    main()
