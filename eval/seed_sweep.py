"""
Seed sweep for E1, E2, E3, E5 (E4 CUSUM is deterministic/cluster-independent).

Runs the full baseline + improved pipelines under a given seed, then computes
in-sample metrics (mirroring eval/metrics.py) and held-out metrics (mirroring
eval/held_out.py) with the seed propagated EVERYWHERE that touches randomness
or the train/test partition:

  - random.seed(seed)
  - np.random.seed(seed)  /  np.random.default_rng(seed + offsets)
  - PYTHONHASHSEED env (set before child interpreters, best-effort here)
  - UMAP random_state=seed
  - HDBSCAN: deterministic; min_cluster_size=20, min_samples=5 explicit
  - SentenceTransformer: deterministic mode via torch manual seed
  - Train/test split salt: hash((trace_id, seed)) % 5 == 0 -> held-out
  - Bootstrap RNGs all derived from seed

Per seed we emit one JSON row to eval/seed_sweep_raw.jsonl with E1, E2, E3, E5
numbers (in-sample + held-out where applicable). Per-seed artifacts go to
eval/seed_sweep_outputs/seed_<S>/. Existing seed-42 artifacts in
baseline/outputs, improved/outputs, and eval/raw_numbers.json are NOT touched.

Usage:  python eval/seed_sweep.py --seed 7
        python eval/seed_sweep.py --summarize   # emit eval/seed_sweep.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW_PATH = ROOT / "eval" / "seed_sweep_raw.jsonl"
SUMMARY_MD = ROOT / "eval" / "seed_sweep.md"
SEED_OUT_BASE = ROOT / "eval" / "seed_sweep_outputs"
TRACES_PATH = ROOT / "sim" / "data" / "traces.jsonl"

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
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

N_BOOT = 1000
CI_LOW, CI_HIGH = 2.5, 97.5

# Reference seed-42 in-sample verdicts (read from eval/raw_numbers.json; used
# for the verdict-stability column).
REF_SEED = 42


# ----------------------------- determinism helpers ---------------------------

def set_global_determinism(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch  # noqa
        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(False)  # MiniLM has nondet ops; tolerate
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def held_out_mask_salted(trace_ids: list[str], seed: int) -> np.ndarray:
    """80/20 split with hash salted by seed so the partition itself moves."""
    out = np.zeros(len(trace_ids), dtype=bool)
    for i, tid in enumerate(trace_ids):
        h = int(hashlib.md5(f"{tid}|{seed}".encode()).hexdigest(), 16)
        out[i] = (h % 5 == 0)
    return out


# ----------------------------- pipeline runners ------------------------------

def load_traces() -> list[dict]:
    out = []
    with TRACES_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def embed(docs: list[str], model) -> np.ndarray:
    embs = model.encode(
        docs, batch_size=64, show_progress_bar=False,
        convert_to_numpy=True, normalize_embeddings=False,
    )
    return embs.astype(np.float32)


def run_full_pipeline(traces: list[dict], build_doc, seed: int, tag: str) -> dict:
    """Embed -> UMAP -> HDBSCAN on FULL dataset (for in-sample)."""
    import hdbscan
    import umap
    from sentence_transformers import SentenceTransformer

    set_global_determinism(seed)
    docs = [build_doc(t) for t in traces]

    model = SentenceTransformer(EMBED_MODEL_NAME)
    embs = embed(docs, model)

    reducer = umap.UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0,
        metric="cosine", random_state=seed,
    )
    coords = reducer.fit_transform(embs)
    clusterer = hdbscan.HDBSCAN(**HDBSCAN_PARAMS)
    labels = clusterer.fit_predict(coords)
    n_clusters = len({c for c in labels if c != -1})
    n_noise = int((labels == -1).sum())
    print(f"[{tag}] in-sample: n_clusters={n_clusters} noise={n_noise}")
    return dict(docs=docs, labels=labels, n_clusters=n_clusters, n_noise=n_noise)


def run_split_pipeline(
    train_traces: list[dict], test_traces: list[dict], build_doc, seed: int, tag: str
) -> dict:
    """Train-fit UMAP/HDBSCAN, predict on held-out."""
    import hdbscan
    import umap
    from sentence_transformers import SentenceTransformer

    set_global_determinism(seed)
    train_docs = [build_doc(t) for t in train_traces]
    test_docs = [build_doc(t) for t in test_traces]

    model = SentenceTransformer(EMBED_MODEL_NAME)
    train_embs = embed(train_docs, model)
    test_embs = embed(test_docs, model)

    reducer = umap.UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0,
        metric="cosine", random_state=seed,
    )
    train_coords = reducer.fit_transform(train_embs)
    test_coords = reducer.transform(test_embs)

    clusterer = hdbscan.HDBSCAN(prediction_data=True, **HDBSCAN_PARAMS)
    train_labels = clusterer.fit_predict(train_coords)
    test_labels, _ = hdbscan.approximate_predict(clusterer, test_coords)

    n_train_clusters = len({c for c in train_labels if c != -1})
    n_train_noise = int((train_labels == -1).sum())
    n_test_noise = int((test_labels == -1).sum())
    print(f"[{tag}] split: train_clusters={n_train_clusters} "
          f"train_noise={n_train_noise} test_noise={n_test_noise}")
    return dict(
        train_labels=train_labels, test_labels=test_labels,
        n_train_clusters=n_train_clusters, n_train_noise=n_train_noise,
        n_test_noise=n_test_noise,
    )


# ----------------------------- metric helpers --------------------------------

def majority_cluster(labels: np.ndarray, idx_list: list[int]) -> int | None:
    counts: Counter = Counter()
    for i in idx_list:
        c = int(labels[i])
        if c != -1:
            counts[c] += 1
    if not counts:
        return None
    mx = max(counts.values())
    return min(c for c, n in counts.items() if n == mx)


def recall_at(labels: np.ndarray, idx_list: list[int], mc: int | None) -> tuple[float, int]:
    if mc is None or not idx_list:
        return 0.0, 0
    hits = sum(1 for i in idx_list if int(labels[i]) == mc)
    return hits / len(idx_list), hits


def boot_mean(ind: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    n = len(ind)
    if n == 0:
        return 0.0, 0.0, 0.0
    pt = float(ind.mean())
    idx = rng.integers(0, n, size=(N_BOOT, n))
    s = ind[idx].mean(axis=1)
    lo, hi = np.percentile(s, [CI_LOW, CI_HIGH])
    return pt, float(lo), float(hi)


def boot_paired(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    n = len(a)
    if n == 0:
        return 0.0, 0.0, 0.0
    pt = float(b.mean() - a.mean())
    idx = rng.integers(0, n, size=(N_BOOT, n))
    d = b[idx].mean(axis=1) - a[idx].mean(axis=1)
    lo, hi = np.percentile(d, [CI_LOW, CI_HIGH])
    return pt, float(lo), float(hi)


# ----------------------------- E5 attribution --------------------------------

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
    mx = max(counts.values())
    for e in reversed(window):
        if counts[e["agent"]] == mx:
            return e["agent"]
    return "unknown"


def backward_walk_top1(labels: np.ndarray, traces: list[dict]) -> dict[int, str]:
    """Per-cluster top-1 suspect agent (same scoring as baseline pipeline)."""
    SW = dict(proximity=0.4, frequency=0.3, bridge=0.2, role=0.1)
    ROLE = defaultdict(lambda: 1.0, {"orchestrator": 0.5})
    WALK_DEPTH = 10
    by_c: dict[int, list[dict]] = defaultdict(list)
    for c, t in zip(labels, traces):
        by_c[int(c)].append(t)
    out: dict[int, str] = {}
    for c, ts in by_c.items():
        if c == -1:
            continue
        prox_sum = Counter(); freq_sum = Counter(); bridge_sum = Counter(); hits = Counter()
        for trace in ts:
            events = trace["events"]
            focus = None
            for i, ev in enumerate(events):
                if ev.get("type") in ("failure", "signal"):
                    focus = i; break
            if focus is None:
                if trace["outcome"] in ("blocked", "failed", "review"):
                    focus = len(events) - 1
                else:
                    continue
            start = max(0, focus - WALK_DEPTH + 1)
            window = events[start: focus + 1]
            wsize = max(1, len(window))
            adj: dict[str, set] = defaultdict(set)
            for ev in window:
                a = ev.get("agent", "?"); to = ev.get("to")
                if to and to != a:
                    adj[a].add(to); adj[to].add(a)
            positions: dict[str, list[int]] = defaultdict(list)
            for off, ev in enumerate(window):
                positions[ev.get("agent", "?")].append(off)
            for agent, ps in positions.items():
                d = [(wsize - 1) - p for p in ps]
                prox = max(1.0 / (1.0 + dd) for dd in d)
                freq = len(ps) / wsize
                bridge = min(1.0, len(adj.get(agent, set())) / 6.0)
                prox_sum[agent] += prox
                freq_sum[agent] += freq
                bridge_sum[agent] += bridge
                hits[agent] += 1
        if not hits:
            continue
        best = (-1.0, None)
        for agent, h in hits.items():
            s = (SW["proximity"] * (prox_sum[agent] / h)
                 + SW["frequency"] * (freq_sum[agent] / h)
                 + SW["bridge"] * (bridge_sum[agent] / h)
                 + SW["role"] * ROLE[agent])
            if s > best[0]:
                best = (s, agent)
        out[c] = best[1]
    return out


# ----------------------------- verdict helpers -------------------------------

def e2_verdict(base_recall: float, impr_recall: float, gap_lo: float, gap_pt: float) -> str:
    # Mirrors metrics.py + held_out.py logic.
    refutes = (base_recall >= 0.35) or (gap_lo <= 0)
    supports = (gap_lo > 0.50) and (base_recall < 0.20) and (impr_recall >= 0.70)
    if supports:
        return "MAGNITUDE SUPPORTED"
    if gap_pt > 0 and not refutes:
        return "DIRECTION CONFIRMED"
    return "REFUTED"


def e3_verdict(base_recall: float, impr_recall: float, gap_lo: float) -> str:
    refutes = (base_recall >= 0.30) or (gap_lo <= 0)
    supports = (gap_lo > 0) and (impr_recall >= 0.65) and (base_recall < 0.30)
    if supports:
        return "SUPPORTS"
    return "REFUTED" if refutes else "REFUTED"


def e1_verdict(sub_recall: float, esc_recall: float) -> str:
    return "SUPPORTS" if (sub_recall >= 0.50 and esc_recall >= 0.50) else "REFUTES"


def e5_verdict(gap_pt: float, gap_lo: float, gap_hi: float) -> str:
    if gap_pt > 0 and gap_lo > 0:
        return "WALK BEATS MFA-5"
    if gap_pt < 0 and gap_hi < 0:
        return "MFA-5 BEATS WALK"
    return "NULL"


# ----------------------------- one-seed driver -------------------------------

def run_one_seed(seed: int) -> dict:
    t0 = time.time()
    out_dir = SEED_OUT_BASE / f"seed_{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Import build_document functions; their module-level SEED variables
    # don't affect the functions themselves (no global RNG use in build_doc).
    from baseline.pipeline import build_document as build_baseline_doc
    from improved.pipeline import build_document as build_improved_doc

    traces = load_traces()
    trace_ids = [t["trace_id"] for t in traces]
    by_id = {t["trace_id"]: i for i, t in enumerate(traces)}

    # ---------- IN-SAMPLE: full-dataset baseline + improved ----------
    res_base_full = run_full_pipeline(traces, build_baseline_doc, seed, f"baseline-s{seed}")
    res_impr_full = run_full_pipeline(traces, build_improved_doc, seed, f"improved-s{seed}")

    # mode index lists
    mode_idx: dict[str, list[int]] = {m: [] for m in FAILURE_MODES}
    for i, t in enumerate(traces):
        for m in (t.get("failure_modes") or []):
            if m in mode_idx:
                mode_idx[m].append(i)

    rng_seed = seed * 7 + 1
    per_mode_full: dict = {}
    for mode in FAILURE_MODES:
        idxs = mode_idx[mode]
        b_mc = majority_cluster(res_base_full["labels"], idxs)
        i_mc = majority_cluster(res_impr_full["labels"], idxs)
        b_r, b_h = recall_at(res_base_full["labels"], idxs, b_mc)
        i_r, i_h = recall_at(res_impr_full["labels"], idxs, i_mc)
        b_ind = np.array(
            [1 if (b_mc is not None and int(res_base_full["labels"][i]) == b_mc) else 0
             for i in idxs], dtype=int)
        i_ind = np.array(
            [1 if (i_mc is not None and int(res_impr_full["labels"][i]) == i_mc) else 0
             for i in idxs], dtype=int)
        gap_pt, gap_lo, gap_hi = boot_paired(b_ind, i_ind, np.random.default_rng(rng_seed))
        rng_seed += 1
        per_mode_full[mode] = dict(
            n=len(idxs),
            baseline=dict(majority_cluster=b_mc, recall=b_r, hits=b_h),
            improved=dict(majority_cluster=i_mc, recall=i_r, hits=i_h),
            gap=dict(point=gap_pt, ci_lo=gap_lo, ci_hi=gap_hi),
        )

    # E1
    e1_sub = per_mode_full["substitution_reroute"]["baseline"]["recall"]
    e1_esc = per_mode_full["escalation_loop"]["baseline"]["recall"]
    e1 = dict(
        substitution_reroute_recall=e1_sub,
        escalation_loop_recall=e1_esc,
        verdict=e1_verdict(e1_sub, e1_esc),
    )

    # E2 (in-sample)
    e2 = per_mode_full["stale_quote_slow_pricing"]
    e2_v = e2_verdict(e2["baseline"]["recall"], e2["improved"]["recall"],
                      e2["gap"]["ci_lo"], e2["gap"]["point"])
    e2_in = dict(
        baseline_recall=e2["baseline"]["recall"],
        improved_recall=e2["improved"]["recall"],
        gap=e2["gap"]["point"], gap_ci=(e2["gap"]["ci_lo"], e2["gap"]["ci_hi"]),
        verdict=e2_v,
    )

    # E3 (in-sample)
    e3 = per_mode_full["compliance_skipped_under_tariff"]
    e3_v = e3_verdict(e3["baseline"]["recall"], e3["improved"]["recall"], e3["gap"]["ci_lo"])
    e3_in = dict(
        baseline_recall=e3["baseline"]["recall"],
        improved_recall=e3["improved"]["recall"],
        gap=e3["gap"]["point"], gap_ci=(e3["gap"]["ci_lo"], e3["gap"]["ci_hi"]),
        verdict=e3_v,
    )

    # E5 (in-sample) - backward walk on baseline clusters
    bw_top1 = backward_walk_top1(res_base_full["labels"], traces)
    struct_idx = mode_idx["substitution_reroute"] + mode_idx["escalation_loop"]
    gt_strict_list = ([GT_AGENT_STRICT["substitution_reroute"]] * len(mode_idx["substitution_reroute"])
                      + [GT_AGENT_STRICT["escalation_loop"]] * len(mode_idx["escalation_loop"]))
    gt_lenient_list = ([GT_AGENT_LENIENT["substitution_reroute"]] * len(mode_idx["substitution_reroute"])
                       + [GT_AGENT_LENIENT["escalation_loop"]] * len(mode_idx["escalation_loop"]))
    mfa_pred, bw_pred = [], []
    for i in struct_idx:
        t = traces[i]
        fi = pick_focus_idx(t["events"])
        mfa_pred.append(mfa_attribution(t["events"], fi, n=5))
        c = int(res_base_full["labels"][i])
        bw_pred.append(bw_top1.get(c, "unknown"))
    mfa_s = np.array([1 if mfa_pred[i] in gt_strict_list[i] else 0 for i in range(len(struct_idx))])
    bw_s = np.array([1 if bw_pred[i] in gt_strict_list[i] else 0 for i in range(len(struct_idx))])
    mfa_l = np.array([1 if mfa_pred[i] in gt_lenient_list[i] else 0 for i in range(len(struct_idx))])
    bw_l = np.array([1 if bw_pred[i] in gt_lenient_list[i] else 0 for i in range(len(struct_idx))])
    g_s = boot_paired(mfa_s, bw_s, np.random.default_rng(seed * 11 + 5))
    g_l = boot_paired(mfa_l, bw_l, np.random.default_rng(seed * 11 + 6))
    e5_in = dict(
        n=len(struct_idx),
        strict=dict(
            mfa5=float(mfa_s.mean()), walk=float(bw_s.mean()),
            gap_walk_minus_mfa5=g_s[0], gap_ci=(g_s[1], g_s[2]),
            verdict=e5_verdict(*g_s),
        ),
        lenient=dict(
            mfa5=float(mfa_l.mean()), walk=float(bw_l.mean()),
            gap_walk_minus_mfa5=g_l[0], gap_ci=(g_l[1], g_l[2]),
            verdict=e5_verdict(*g_l),
        ),
    )

    # ---------- HELD-OUT split (salted by seed) ----------
    mask_test = held_out_mask_salted(trace_ids, seed)
    train_idx = np.where(~mask_test)[0]
    test_idx = np.where(mask_test)[0]
    train_traces = [traces[i] for i in train_idx]
    test_traces = [traces[i] for i in test_idx]
    print(f"[seed={seed}] split: train={len(train_traces)} test={len(test_traces)}")

    res_b = run_split_pipeline(train_traces, test_traces, build_baseline_doc, seed,
                               f"baseline-split-s{seed}")
    res_i = run_split_pipeline(train_traces, test_traces, build_improved_doc, seed,
                               f"improved-split-s{seed}")

    # E2 held-out
    mode = "stale_quote_slow_pricing"
    train_with_mode = [i for i, t in enumerate(train_traces) if mode in (t.get("failure_modes") or [])]
    test_with_mode = [i for i, t in enumerate(test_traces) if mode in (t.get("failure_modes") or [])]
    b_mc = majority_cluster(res_b["train_labels"], train_with_mode)
    i_mc = majority_cluster(res_i["train_labels"], train_with_mode)
    b_train_r, _ = recall_at(res_b["train_labels"], train_with_mode, b_mc)
    i_train_r, _ = recall_at(res_i["train_labels"], train_with_mode, i_mc)
    b_test_r, _ = recall_at(res_b["test_labels"], test_with_mode, b_mc)
    i_test_r, _ = recall_at(res_i["test_labels"], test_with_mode, i_mc)
    if test_with_mode and b_mc is not None and i_mc is not None:
        ind_b = np.array([1 if int(res_b["test_labels"][i]) == b_mc else 0 for i in test_with_mode])
        ind_i = np.array([1 if int(res_i["test_labels"][i]) == i_mc else 0 for i in test_with_mode])
        e2_held_gap_pt, e2_held_gap_lo, e2_held_gap_hi = boot_paired(
            ind_b, ind_i, np.random.default_rng(seed * 13 + 2))
    else:
        e2_held_gap_pt = i_test_r - b_test_r
        e2_held_gap_lo = e2_held_gap_hi = 0.0
    e2_train_gap = i_train_r - b_train_r
    e2_train_v = e2_verdict(b_train_r, i_train_r, e2_train_gap, e2_train_gap)  # in-sample uses point gap as proxy
    # Actually mirror metrics.py: needs CI. Recompute paired bootstrap on train for verdict CI.
    if train_with_mode:
        ind_b_tr = np.array([1 if int(res_b["train_labels"][i]) == b_mc else 0 for i in train_with_mode])
        ind_i_tr = np.array([1 if int(res_i["train_labels"][i]) == i_mc else 0 for i in train_with_mode])
        gp, glo, ghi = boot_paired(ind_b_tr, ind_i_tr, np.random.default_rng(seed * 13 + 7))
        e2_train_v = e2_verdict(b_train_r, i_train_r, glo, gp)
    e2_held_v = e2_verdict(b_test_r, i_test_r, e2_held_gap_lo, e2_held_gap_pt)
    e2_held = dict(
        train_baseline=b_train_r, train_improved=i_train_r, train_gap=e2_train_gap,
        train_verdict=e2_train_v,
        held_baseline=b_test_r, held_improved=i_test_r, held_gap=e2_held_gap_pt,
        held_ci=(e2_held_gap_lo, e2_held_gap_hi), held_verdict=e2_held_v,
    )

    # E5 held-out
    bw_top1_train = backward_walk_top1(res_b["train_labels"], train_traces)
    struct_test = [i for i, t in enumerate(test_traces)
                   if any(m in (t.get("failure_modes") or [])
                          for m in ("substitution_reroute", "escalation_loop"))]
    mfa_p, bw_p, gt_s, gt_l = [], [], [], []
    for i in struct_test:
        t = test_traces[i]
        modes = t.get("failure_modes") or []
        fi = pick_focus_idx(t["events"])
        mfa_p.append(mfa_attribution(t["events"], fi, 5))
        c = int(res_b["test_labels"][i])
        bw_p.append(bw_top1_train.get(c, "unknown"))
        ss, ll = set(), set()
        for m in modes:
            if m in GT_AGENT_STRICT:
                ss |= GT_AGENT_STRICT[m]; ll |= GT_AGENT_LENIENT[m]
        gt_s.append(ss); gt_l.append(ll)
    n5 = len(struct_test)
    if n5 > 0:
        ms = np.array([1 if mfa_p[i] in gt_s[i] else 0 for i in range(n5)])
        bs = np.array([1 if bw_p[i] in gt_s[i] else 0 for i in range(n5)])
        ml = np.array([1 if mfa_p[i] in gt_l[i] else 0 for i in range(n5)])
        bl = np.array([1 if bw_p[i] in gt_l[i] else 0 for i in range(n5)])
        gs = boot_paired(ms, bs, np.random.default_rng(seed * 17 + 1))
        gl = boot_paired(ml, bl, np.random.default_rng(seed * 17 + 2))
        e5_held = dict(
            n=n5,
            strict=dict(mfa5=float(ms.mean()), walk=float(bs.mean()),
                        gap_walk_minus_mfa5=gs[0], gap_ci=(gs[1], gs[2]),
                        verdict=e5_verdict(*gs)),
            lenient=dict(mfa5=float(ml.mean()), walk=float(bl.mean()),
                         gap_walk_minus_mfa5=gl[0], gap_ci=(gl[1], gl[2]),
                         verdict=e5_verdict(*gl)),
        )
    else:
        e5_held = dict(n=0, strict=dict(verdict="N/A"), lenient=dict(verdict="N/A"))

    runtime = time.time() - t0
    row = dict(
        seed=seed,
        runtime_seconds=runtime,
        n_traces=len(traces),
        n_train=len(train_traces), n_test=len(test_traces),
        n_clusters_baseline_full=res_base_full["n_clusters"],
        n_clusters_improved_full=res_impr_full["n_clusters"],
        n_clusters_baseline_train=res_b["n_train_clusters"],
        n_clusters_improved_train=res_i["n_train_clusters"],
        E1=e1,
        E2_in_sample=e2_in,
        E2_held_out=e2_held,
        E3_in_sample=e3_in,
        E5_in_sample=e5_in,
        E5_held_out=e5_held,
        per_mode_full=per_mode_full,
    )
    # Per-seed artifact
    (out_dir / "seed_metrics.json").write_text(json.dumps(row, indent=2, default=str))
    print(f"[seed={seed}] wrote {out_dir/'seed_metrics.json'} in {runtime:.1f}s")
    return row


def append_raw(row: dict) -> None:
    # Replace any existing row for this seed, then append.
    existing = []
    if RAW_PATH.exists():
        for line in RAW_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get("seed") != row["seed"]:
                    existing.append(r)
            except json.JSONDecodeError:
                continue
    existing.append(row)
    with RAW_PATH.open("w") as f:
        for r in existing:
            f.write(json.dumps(r, default=str) + "\n")


# ----------------------------- summarize -------------------------------------

def summarize() -> None:
    rows: list[dict] = []
    if RAW_PATH.exists():
        for line in RAW_PATH.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["seed"])
    seeds = [r["seed"] for r in rows]

    # Reference seed-42 verdicts come from this sweep's seed_42 row when present.
    ref_row = next((r for r in rows if r["seed"] == REF_SEED), None)

    def fmt(x, p=3):
        try:
            return f"{x:+.{p}f}" if x is not None else "—"
        except Exception:
            return str(x)

    def verdict_stability(verdicts: list[str], ref: str) -> str:
        same = sum(1 for v in verdicts if v == ref)
        if same == len(verdicts):
            return "ROBUST"
        # majority differs?
        from collections import Counter as C
        c = C(verdicts)
        mode_v, _ = c.most_common(1)[0]
        if mode_v != ref and c[mode_v] > len(verdicts) // 2:
            return "REVERSED"
        return "MIXED"

    lines: list[str] = []
    lines.append("# Seed sweep results (E1, E2, E3, E5)\n")
    lines.append(f"Seeds run: {seeds}.  E4 omitted: CUSUM drift detector is "
                 "deterministic and cluster-independent; seed has no effect on it.\n")
    lines.append("Per-seed artifacts in `eval/seed_sweep_outputs/seed_<S>/`. Raw rows "
                 "in `eval/seed_sweep_raw.jsonl`. The train/test partition is salted "
                 "by seed (`hash((trace_id, seed)) % 5 == 0` -> held-out), so even the "
                 "20% held-out *set* changes between seeds, not just the cluster fit.\n")

    # ---------- E1 ----------
    lines.append("## E1 — baseline structural recall\n")
    lines.append("Per-seed recall@cluster for substitution_reroute and escalation_loop "
                 "(baseline pipeline, full dataset). Verdict = SUPPORTS iff both >= 0.50.\n")
    header = "| Metric | " + " | ".join(f"Seed {s}" for s in seeds) + " | Range | Verdict-stability |"
    sep = "|" + "---|" * (len(seeds) + 3)
    lines.append(header); lines.append(sep)
    sub = [r["E1"]["substitution_reroute_recall"] for r in rows]
    esc = [r["E1"]["escalation_loop_recall"] for r in rows]
    e1_verds = [r["E1"]["verdict"] for r in rows]
    ref_e1 = ref_row["E1"]["verdict"] if ref_row else e1_verds[0]
    lines.append(f"| substitution recall | " + " | ".join(f"{x:.3f}" for x in sub)
                 + f" | [{min(sub):.3f}, {max(sub):.3f}] | — |")
    lines.append(f"| escalation recall | " + " | ".join(f"{x:.3f}" for x in esc)
                 + f" | [{min(esc):.3f}, {max(esc):.3f}] | — |")
    lines.append(f"| **E1 verdict** | " + " | ".join(e1_verds)
                 + f" | — | **{verdict_stability(e1_verds, ref_e1)}** |\n")

    # ---------- E2 ----------
    lines.append("## E2 — H1 temporal (stale_quote_slow_pricing)\n")
    lines.append("In-sample gap = improved − baseline recall@cluster on full dataset. "
                 "Held-out gap = improved − baseline on the 20% test partition fit on the 80% train. "
                 "Verdict thresholds: MAGNITUDE SUPPORTED (gap CI_lo > 0.50, baseline < 0.20, "
                 "improved >= 0.70); DIRECTION CONFIRMED (positive gap, not refuted); "
                 "REFUTED otherwise.\n")
    e2_in_gaps = [r["E2_in_sample"]["gap"] for r in rows]
    e2_in_verds = [r["E2_in_sample"]["verdict"] for r in rows]
    e2_h_gaps = [r["E2_held_out"]["held_gap"] for r in rows]
    e2_h_verds = [r["E2_held_out"]["held_verdict"] for r in rows]
    ref_e2_in = ref_row["E2_in_sample"]["verdict"] if ref_row else e2_in_verds[0]
    ref_e2_h = ref_row["E2_held_out"]["held_verdict"] if ref_row else e2_h_verds[0]
    lines.append(header); lines.append(sep)
    lines.append(f"| in-sample gap | " + " | ".join(fmt(x) for x in e2_in_gaps)
                 + f" | [{fmt(min(e2_in_gaps))}, {fmt(max(e2_in_gaps))}] | — |")
    lines.append(f"| in-sample verdict | " + " | ".join(e2_in_verds)
                 + f" | — | **{verdict_stability(e2_in_verds, ref_e2_in)}** |")
    lines.append(f"| held-out gap | " + " | ".join(fmt(x) for x in e2_h_gaps)
                 + f" | [{fmt(min(e2_h_gaps))}, {fmt(max(e2_h_gaps))}] | — |")
    lines.append(f"| held-out verdict | " + " | ".join(e2_h_verds)
                 + f" | — | **{verdict_stability(e2_h_verds, ref_e2_h)}** |\n")

    # ---------- E3 ----------
    lines.append("## E3 — H2 omission (compliance_skipped_under_tariff)\n")
    e3_in_gaps = [r["E3_in_sample"]["gap"] for r in rows]
    e3_in_verds = [r["E3_in_sample"]["verdict"] for r in rows]
    ref_e3 = ref_row["E3_in_sample"]["verdict"] if ref_row else e3_in_verds[0]
    lines.append(header); lines.append(sep)
    lines.append(f"| in-sample gap | " + " | ".join(fmt(x) for x in e3_in_gaps)
                 + f" | [{fmt(min(e3_in_gaps))}, {fmt(max(e3_in_gaps))}] | — |")
    lines.append(f"| in-sample verdict | " + " | ".join(e3_in_verds)
                 + f" | — | **{verdict_stability(e3_in_verds, ref_e3)}** |\n")

    # ---------- E5 ----------
    lines.append("## E5 — backward walk vs MFA-5 (the headline finding)\n")
    lines.append("Gap = backward_walk_precision@1 − MFA-5_precision@1 over structural "
                 "traces (substitution_reroute + escalation_loop). Lenient ground truth "
                 "is the load-bearing one (escalation_loop GT = {compliance, release}).\n")
    e5l_gaps = [r["E5_in_sample"]["lenient"]["gap_walk_minus_mfa5"] for r in rows]
    e5l_verds = [r["E5_in_sample"]["lenient"]["verdict"] for r in rows]
    e5s_gaps = [r["E5_in_sample"]["strict"]["gap_walk_minus_mfa5"] for r in rows]
    e5s_verds = [r["E5_in_sample"]["strict"]["verdict"] for r in rows]
    ref_e5l = ref_row["E5_in_sample"]["lenient"]["verdict"] if ref_row else e5l_verds[0]
    ref_e5s = ref_row["E5_in_sample"]["strict"]["verdict"] if ref_row else e5s_verds[0]
    lines.append(header); lines.append(sep)
    lines.append(f"| in-sample lenient gap | " + " | ".join(fmt(x) for x in e5l_gaps)
                 + f" | [{fmt(min(e5l_gaps))}, {fmt(max(e5l_gaps))}] | — |")
    lines.append(f"| in-sample lenient verdict | " + " | ".join(e5l_verds)
                 + f" | — | **{verdict_stability(e5l_verds, ref_e5l)}** |")
    lines.append(f"| in-sample strict gap | " + " | ".join(fmt(x) for x in e5s_gaps)
                 + f" | [{fmt(min(e5s_gaps))}, {fmt(max(e5s_gaps))}] | — |")
    lines.append(f"| in-sample strict verdict | " + " | ".join(e5s_verds)
                 + f" | — | **{verdict_stability(e5s_verds, ref_e5s)}** |\n")

    # Honest framing notes
    lines.append("## Interpretation\n")
    e5l_stab = verdict_stability(e5l_verds, ref_e5l)
    if e5l_stab == "ROBUST" and ref_e5l == "MFA-5 BEATS WALK":
        lines.append("**E5 lenient verdict is ROBUST across all five seeds: the backward "
                     "walk loses to MFA-5 in every seed tested.** The article's headline "
                     "finding hardens to a robust empirical claim, not a single-seed "
                     "artifact.\n")
    elif e5l_stab == "MIXED":
        lines.append("**E5 lenient verdict is MIXED across seeds.** The article's headline "
                     "finding does not generalize cleanly; the per-seed table above shows "
                     "which seeds dissent.\n")
    elif e5l_stab == "REVERSED":
        lines.append("**E5 lenient verdict is REVERSED across the majority of seeds.** The "
                     "article's headline finding does not survive seed replication and must "
                     "be retracted or heavily qualified.\n")
    else:
        lines.append(f"**E5 lenient verdict stability: {e5l_stab}.**\n")

    e2_in_stab = verdict_stability(e2_in_verds, ref_e2_in)
    e2_h_stab = verdict_stability(e2_h_verds, ref_e2_h)
    if e2_h_stab == "ROBUST" and ref_e2_h == "REFUTED":
        lines.append("**E2 held-out reversal is ROBUST: every seed refutes E2 on held-out.** "
                     "The in-sample positive direction on seed 42 does not survive the 80/20 "
                     "cut in any seed; the in-sample H1 effect is broadly fragile, not a "
                     "single-seed quirk.\n")
    elif e2_h_stab == "MIXED":
        lines.append("**E2 held-out verdict is MIXED across seeds.** The seed-42 held-out "
                     "reversal is at least partially seed-dependent; some seeds reverse, "
                     "others do not.\n")
    else:
        lines.append(f"**E2 held-out verdict stability: {e2_h_stab}.** "
                     f"In-sample E2 stability: {e2_in_stab}.\n")

    # ---------- Failure footer ----------
    failed = [r for r in rows if r.get("error")]
    if failed:
        lines.append("## Failed seeds\n")
        for r in failed:
            lines.append(f"- seed {r['seed']}: {r['error']}")
    lines.append("")

    SUMMARY_MD.write_text("\n".join(lines))
    print(f"wrote {SUMMARY_MD}")


# ----------------------------- CLI -------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()

    if args.summarize:
        summarize()
        return
    if args.seed is None:
        ap.error("--seed required (or pass --summarize)")

    try:
        row = run_one_seed(args.seed)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[seed={args.seed}] FAILED: {e}\n{tb}", file=sys.stderr)
        row = dict(seed=args.seed, error=str(e), traceback=tb)
    append_raw(row)


if __name__ == "__main__":
    main()
