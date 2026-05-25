"""Pre-registered metrics for E1-E6.

Run: `python eval/metrics.py`

Reads:
  - /Users/john/macro-evals-response/sim/data/traces.jsonl
  - /Users/john/macro-evals-response/baseline/outputs/clusters.jsonl, suspects.csv
  - /Users/john/macro-evals-response/improved/outputs/clusters.jsonl, suspects.csv, drift_alerts.csv

Writes:
  - /Users/john/macro-evals-response/eval/raw_numbers.json

All metric definitions and thresholds are frozen in preregistration.md.
Seed = 42, n_resamples = 1000, percentile CIs at 95%.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path("/Users/john/macro-evals-response")
TRACES_PATH = ROOT / "sim" / "data" / "traces.jsonl"
BASELINE_DIR = ROOT / "baseline" / "outputs"
IMPROVED_DIR = ROOT / "improved" / "outputs"
OUT_JSON = ROOT / "eval" / "raw_numbers.json"

SEED = 42
N_BOOT = 1000
CI_LOW, CI_HIGH = 2.5, 97.5

FAILURE_MODES = [
    "substitution_reroute",
    "compliance_skipped_under_tariff",
    "stale_quote_slow_pricing",
    "pricing_drift",
    "escalation_loop",
    "random_noise_failure",
]

# Pre-registered ground-truth causal-agent mapping (preregistration.md).
GT_AGENT_STRICT = {
    "substitution_reroute": {"supply"},
    "escalation_loop": {"compliance"},
}
GT_AGENT_LENIENT = {
    "substitution_reroute": {"supply"},
    "escalation_loop": {"compliance", "release"},
}


# ---------- I/O ----------

def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f]


def load_clusters(path: Path) -> dict[str, int]:
    """trace_id -> cluster_id."""
    out = {}
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            out[row["trace_id"]] = row["cluster_id"]
    return out


def load_suspects_top1(path: Path) -> dict[int, str]:
    """cluster -> top-1 agent (max suspect_score; ties broken by csv order which is score-sorted)."""
    best: dict[int, tuple[float, str]] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            c = int(row["cluster"])
            score = float(row["suspect_score"])
            agent = row["agent"]
            if c not in best or score > best[c][0]:
                best[c] = (score, agent)
    return {c: a for c, (_, a) in best.items()}


# ---------- Core metric: majority cluster + recall@cluster ----------

def majority_cluster(trace_clusters: dict[str, int], trace_ids_with_F: list[str]) -> int | None:
    """Plurality cluster among trace_ids_with_F, excluding -1. Tie-break: smaller cluster_id wins."""
    counts: Counter = Counter()
    for tid in trace_ids_with_F:
        c = trace_clusters.get(tid)
        if c is None or c == -1:
            continue
        counts[c] += 1
    if not counts:
        return None
    max_count = max(counts.values())
    candidates = [c for c, n in counts.items() if n == max_count]
    return min(candidates)


def recall_at_cluster(trace_clusters: dict[str, int], trace_ids_with_F: list[str]) -> tuple[float, int | None]:
    mc = majority_cluster(trace_clusters, trace_ids_with_F)
    if mc is None or not trace_ids_with_F:
        return 0.0, mc
    hits = sum(1 for tid in trace_ids_with_F if trace_clusters.get(tid) == mc)
    return hits / len(trace_ids_with_F), mc


# ---------- Bootstrap ----------

def bootstrap_indicator_mean(indicator: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    """indicator: 0/1 array of length n. Returns (point, ci_lo, ci_hi)."""
    n = len(indicator)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = float(indicator.mean())
    idx = rng.integers(0, n, size=(N_BOOT, n))
    samples = indicator[idx].mean(axis=1)
    lo, hi = np.percentile(samples, [CI_LOW, CI_HIGH])
    return point, float(lo), float(hi)


def bootstrap_paired_gap(ind_a: np.ndarray, ind_b: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    """Gap = mean(ind_b) - mean(ind_a) with paired resampling. Returns (point, ci_lo, ci_hi)."""
    assert len(ind_a) == len(ind_b)
    n = len(ind_a)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = float(ind_b.mean() - ind_a.mean())
    idx = rng.integers(0, n, size=(N_BOOT, n))
    diffs = ind_b[idx].mean(axis=1) - ind_a[idx].mean(axis=1)
    lo, hi = np.percentile(diffs, [CI_LOW, CI_HIGH])
    return point, float(lo), float(hi)


# ---------- Recall@cluster indicator vector for bootstrap ----------

def recall_indicator(trace_clusters: dict[str, int], trace_ids_with_F: list[str]) -> tuple[np.ndarray, int | None]:
    mc = majority_cluster(trace_clusters, trace_ids_with_F)
    if mc is None:
        return np.zeros(len(trace_ids_with_F), dtype=int), None
    arr = np.array([1 if trace_clusters.get(tid) == mc else 0 for tid in trace_ids_with_F], dtype=int)
    return arr, mc


# ---------- E5: MFA-5 and backward-walk attribution ----------

def pick_focus_idx(events: list[dict], outcome: str) -> int:
    """Per preregistration:
       1. first 'signal'-type event, else
       2. if outcome in {blocked, review}, last event in trace, else
       3. last event in trace.
    """
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
    # Tie-break: latest occurrence wins (scan reversed window)
    for e in reversed(window):
        if counts[e["agent"]] == max_count:
            return e["agent"]
    return "unknown"


def main():
    rng = np.random.default_rng(SEED)
    traces = load_jsonl(TRACES_PATH)
    by_id = {t["trace_id"]: t for t in traces}

    baseline_clusters = load_clusters(BASELINE_DIR / "clusters.jsonl")
    improved_clusters = load_clusters(IMPROVED_DIR / "clusters.jsonl")
    baseline_suspects = load_suspects_top1(BASELINE_DIR / "suspects.csv")
    improved_suspects = load_suspects_top1(IMPROVED_DIR / "suspects.csv")  # not used for E5 primary

    # Build per-failure-mode trace lists
    mode_tids: dict[str, list[str]] = {m: [] for m in FAILURE_MODES}
    for t in traces:
        for m in t.get("failure_modes", []):
            if m in mode_tids:
                mode_tids[m].append(t["trace_id"])

    results: dict = {
        "seed": SEED,
        "n_resamples": N_BOOT,
        "ci_level": 0.95,
        "ci_method": "percentile",
        "n_traces": len(traces),
        "mode_counts": {m: len(v) for m, v in mode_tids.items()},
    }

    # ---------- E1: baseline recall on structural ----------
    e1: dict = {}
    for mode in ["substitution_reroute", "escalation_loop"]:
        tids = mode_tids[mode]
        ind, mc = recall_indicator(baseline_clusters, tids)
        point, lo, hi = bootstrap_indicator_mean(ind, rng)
        e1[mode] = {
            "n_traces_with_mode": len(tids),
            "majority_cluster": mc,
            "recall_at_cluster": point,
            "ci_lo": lo, "ci_hi": hi,
        }
    e1["verdict"] = (
        "SUPPORTS" if (e1["substitution_reroute"]["recall_at_cluster"] >= 0.50
                        and e1["escalation_loop"]["recall_at_cluster"] >= 0.50)
        else "REFUTES"
    )
    results["E1"] = e1

    # ---------- E2/E3/E6 helpers: per-mode paired gap ----------
    per_mode_full: dict = {}
    for mode in FAILURE_MODES:
        tids = mode_tids[mode]
        if not tids:
            per_mode_full[mode] = None
            continue
        base_ind, base_mc = recall_indicator(baseline_clusters, tids)
        impr_ind, impr_mc = recall_indicator(improved_clusters, tids)
        base_point, base_lo, base_hi = bootstrap_indicator_mean(base_ind, np.random.default_rng(SEED))
        impr_point, impr_lo, impr_hi = bootstrap_indicator_mean(impr_ind, np.random.default_rng(SEED + 1))
        gap_point, gap_lo, gap_hi = bootstrap_paired_gap(base_ind, impr_ind, np.random.default_rng(SEED + 2))
        per_mode_full[mode] = {
            "n_traces_with_mode": len(tids),
            "baseline": {
                "majority_cluster": base_mc,
                "recall_at_cluster": base_point,
                "ci_lo": base_lo, "ci_hi": base_hi,
            },
            "improved": {
                "majority_cluster": impr_mc,
                "recall_at_cluster": impr_point,
                "ci_lo": impr_lo, "ci_hi": impr_hi,
            },
            "gap_improved_minus_baseline": {
                "point": gap_point, "ci_lo": gap_lo, "ci_hi": gap_hi,
            },
        }
    results["per_mode"] = per_mode_full

    # ---------- E2: H1 ----------
    e2 = dict(per_mode_full["stale_quote_slow_pricing"])
    base = e2["baseline"]["recall_at_cluster"]
    impr = e2["improved"]["recall_at_cluster"]
    gap_lo = e2["gap_improved_minus_baseline"]["ci_lo"]
    # SUPPORTS: gap CI lower > 0.50 AND baseline < 0.20 AND improved >= 0.70
    # REFUTES: baseline >= 0.35 OR gap CI lower <= 0
    refutes = (base >= 0.35) or (gap_lo <= 0)
    supports = (gap_lo > 0.50) and (base < 0.20) and (impr >= 0.70)
    e2["verdict"] = "REFUTES" if refutes else ("SUPPORTS" if supports else "REFUTES")  # if neither, treat as REFUTES (no hedging)
    e2["thresholds"] = {
        "supports": "gap_ci_lo > 0.50 AND baseline < 0.20 AND improved >= 0.70",
        "refutes": "baseline >= 0.35 OR gap_ci_lo <= 0",
    }
    results["E2"] = e2

    # ---------- E3: H2 ----------
    e3 = dict(per_mode_full["compliance_skipped_under_tariff"])
    base = e3["baseline"]["recall_at_cluster"]
    impr = e3["improved"]["recall_at_cluster"]
    gap_lo = e3["gap_improved_minus_baseline"]["ci_lo"]
    refutes = (base >= 0.30) or (gap_lo <= 0)
    supports = (gap_lo > 0) and (impr >= 0.65) and (base < 0.30)
    e3["verdict"] = "REFUTES" if refutes else ("SUPPORTS" if supports else "REFUTES")
    e3["thresholds"] = {
        "supports": "gap_ci_lo > 0 AND improved >= 0.65 AND baseline < 0.30",
        "refutes": "baseline >= 0.30 OR gap_ci_lo <= 0",
    }
    results["E3"] = e3

    # ---------- E4: drift detection ----------
    drift_alerts_path = IMPROVED_DIR / "drift_alerts.csv"
    alerts: list[dict] = []
    with drift_alerts_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["alert_day"] = int(row["alert_day"])
            alerts.append(row)
    earliest = min(alerts, key=lambda r: r["alert_day"]) if alerts else None
    e4 = {
        "baseline_alert_day": math.inf,
        "baseline_note": "No drift detector in baseline pipeline outputs (no drift_alerts.csv).",
        "improved_alert_day": earliest["alert_day"] if earliest else None,
        "improved_first_stratum": earliest["cluster_id"] if earliest else None,
        "improved_signal": earliest["signal_name"] if earliest else None,
        "injection_day": 45,
        "days_to_detection_improved": (earliest["alert_day"] - 45) if earliest else None,
        "all_alerts": alerts,
    }
    if e4["improved_alert_day"] is None:
        e4["verdict"] = "REFUTES"
    elif e4["improved_alert_day"] <= 52:
        e4["verdict"] = "SUPPORTS"
    elif e4["improved_alert_day"] <= 75:
        e4["verdict"] = "SUPPORTS"
        e4["note"] = f"Detected within {e4['days_to_detection_improved']} days of injection (not within one week)."
    else:
        e4["verdict"] = "REFUTES"
    results["E4"] = e4

    # ---------- E5: backward walk vs MFA-5 ----------
    structural_tids: list[str] = []
    gt_strict: list[set[str]] = []
    gt_lenient: list[set[str]] = []
    for mode in ["substitution_reroute", "escalation_loop"]:
        for tid in mode_tids[mode]:
            structural_tids.append(tid)
            gt_strict.append(GT_AGENT_STRICT[mode])
            gt_lenient.append(GT_AGENT_LENIENT[mode])

    # MFA-5 predictions
    mfa_pred = []
    for tid in structural_tids:
        t = by_id[tid]
        fi = pick_focus_idx(t["events"], t["outcome"])
        mfa_pred.append(mfa_attribution(t["events"], fi, n=5))

    # Backward-walk predictions (per cluster top-1)
    bw_pred = []
    for tid in structural_tids:
        c = baseline_clusters.get(tid, -1)
        bw_pred.append(baseline_suspects.get(c, "unknown"))

    mfa_ind_strict = np.array([1 if mfa_pred[i] in gt_strict[i] else 0 for i in range(len(structural_tids))])
    bw_ind_strict = np.array([1 if bw_pred[i] in gt_strict[i] else 0 for i in range(len(structural_tids))])
    mfa_ind_lenient = np.array([1 if mfa_pred[i] in gt_lenient[i] else 0 for i in range(len(structural_tids))])
    bw_ind_lenient = np.array([1 if bw_pred[i] in gt_lenient[i] else 0 for i in range(len(structural_tids))])

    mfa_p, mfa_lo, mfa_hi = bootstrap_indicator_mean(mfa_ind_strict, np.random.default_rng(SEED + 10))
    bw_p, bw_lo, bw_hi = bootstrap_indicator_mean(bw_ind_strict, np.random.default_rng(SEED + 11))
    gap_p, gap_lo, gap_hi = bootstrap_paired_gap(mfa_ind_strict, bw_ind_strict, np.random.default_rng(SEED + 12))

    mfa_pl, mfa_lol, mfa_hil = bootstrap_indicator_mean(mfa_ind_lenient, np.random.default_rng(SEED + 13))
    bw_pl, bw_lol, bw_hil = bootstrap_indicator_mean(bw_ind_lenient, np.random.default_rng(SEED + 14))
    gap_pl, gap_lol, gap_hil = bootstrap_paired_gap(mfa_ind_lenient, bw_ind_lenient, np.random.default_rng(SEED + 15))

    # Per-mode breakdown (strict)
    per_mode_e5: dict = {}
    cursor = 0
    for mode in ["substitution_reroute", "escalation_loop"]:
        n = len(mode_tids[mode])
        sl = slice(cursor, cursor + n)
        per_mode_e5[mode] = {
            "n": n,
            "mfa5_precision_at_1_strict": float(mfa_ind_strict[sl].mean()) if n else None,
            "backward_walk_precision_at_1_strict": float(bw_ind_strict[sl].mean()) if n else None,
            "mfa5_top1_distribution": dict(Counter(mfa_pred[sl])),
            "backward_walk_top1_distribution": dict(Counter(bw_pred[sl])),
        }
        cursor += n

    e5 = {
        "n_structural_traces": len(structural_tids),
        "strict": {
            "mfa5_precision_at_1": mfa_p, "mfa5_ci_lo": mfa_lo, "mfa5_ci_hi": mfa_hi,
            "backward_walk_precision_at_1": bw_p, "bw_ci_lo": bw_lo, "bw_ci_hi": bw_hi,
            "gap_bw_minus_mfa5": gap_p, "gap_ci_lo": gap_lo, "gap_ci_hi": gap_hi,
        },
        "lenient": {
            "mfa5_precision_at_1": mfa_pl, "mfa5_ci_lo": mfa_lol, "mfa5_ci_hi": mfa_hil,
            "backward_walk_precision_at_1": bw_pl, "bw_ci_lo": bw_lol, "bw_ci_hi": bw_hil,
            "gap_bw_minus_mfa5": gap_pl, "gap_ci_lo": gap_lol, "gap_ci_hi": gap_hil,
        },
        "per_mode": per_mode_e5,
    }
    # Verdict on cookbook claim: needs gap >= +0.15 AND CI lower > 0 (strict).
    if gap_p >= 0.15 and gap_lo > 0:
        e5["verdict"] = "SUPPORTS"
        e5["interpretation"] = "The backward walk earns its complexity."
    else:
        e5["verdict"] = "REFUTES"
        e5["interpretation"] = "The backward walk is decorative at current complexity. The article will state this."
    if mfa_p < 0.40:
        e5["mfa5_floor_warning"] = (
            "MFA-5 precision@1 < 0.40: structural failures may not be recoverable by any event-local attribution strategy."
        )
    results["E5"] = e5

    # ---------- E6: adversarial check ----------
    e6: dict = {"per_mode": {}}
    for mode in FAILURE_MODES:
        if per_mode_full[mode] is None:
            continue
        gap = per_mode_full[mode]["gap_improved_minus_baseline"]
        regressed = gap["ci_hi"] < 0
        soft = (gap["point"] < 0) and not regressed
        e6["per_mode"][mode] = {
            "gap_point": gap["point"], "gap_ci_lo": gap["ci_lo"], "gap_ci_hi": gap["ci_hi"],
            "regression": regressed, "soft_regression": soft,
        }
    e6["any_regression"] = any(v["regression"] for v in e6["per_mode"].values())
    e6["any_soft_regression"] = any(v["soft_regression"] for v in e6["per_mode"].values())
    e6["verdict"] = "REGRESSION_FOUND" if e6["any_regression"] else (
        "SOFT_REGRESSION_ONLY" if e6["any_soft_regression"] else "NO_REGRESSION"
    )
    results["E6"] = e6

    # Write raw_numbers.json
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"Wrote {OUT_JSON}")

    # Console summary
    print("\n=== Verdicts ===")
    print(f"E1: {results['E1']['verdict']}")
    print(f"E2: {results['E2']['verdict']}")
    print(f"E3: {results['E3']['verdict']}")
    print(f"E4: {results['E4']['verdict']}")
    print(f"E5: {results['E5']['verdict']}")
    print(f"E6: {results['E6']['verdict']}")


if __name__ == "__main__":
    main()
