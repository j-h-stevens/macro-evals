"""Generate static PNGs used in article.md.

  - figures/cluster_failure_matrix.png : 6-mode x top-N cluster heatmap,
    side-by-side panels (baseline vs improved). Cell = recall (fraction of
    mode's traces in that cluster).
  - figures/cluster_116_composition.png : single stacked bar for cluster 116.

Run: `python3 figures/make_figures.py`
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

FAILURE_MODES = [
    "substitution_reroute",
    "compliance_skipped_under_tariff",
    "stale_quote_slow_pricing",
    "pricing_drift",
    "escalation_loop",
    "random_noise_failure",
]
SHORT = {
    "substitution_reroute": "sub_reroute",
    "compliance_skipped_under_tariff": "CSK",
    "stale_quote_slow_pricing": "stale_quote",
    "pricing_drift": "drift",
    "escalation_loop": "esc_loop",
    "random_noise_failure": "noise",
}

TOP_N = 8


def load_cluster_x_mode(path: Path):
    """Return dict[cluster] -> dict[mode] -> count, plus dict[cluster] -> size."""
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    size = {int(r["cluster"]): int(r["cluster_size"]) for r in rows}
    counts: dict[int, dict[str, int]] = {}
    for r in rows:
        c = int(r["cluster"])
        counts[c] = {m: int(r[m]) for m in FAILURE_MODES}
    return counts, size


def mode_totals():
    """ground truth mode totals (n traces with mode)."""
    return {
        "substitution_reroute": 406,
        "compliance_skipped_under_tariff": 247,
        "stale_quote_slow_pricing": 195,
        "pricing_drift": 2666,
        "escalation_loop": 143,
        "random_noise_failure": 311,
    }


def cluster_failure_matrix():
    baseline_counts, baseline_size = load_cluster_x_mode(
        ROOT / "baseline" / "outputs" / "cluster_x_failure_mode.csv"
    )
    impr_counts, impr_size = load_cluster_x_mode(
        ROOT / "improved" / "outputs" / "cluster_x_failure_mode.csv"
    )
    totals = mode_totals()

    def top_clusters(counts, size, n):
        # exclude noise (-1)
        nonnoise = {c: s for c, s in size.items() if c != -1}
        return [c for c, _ in sorted(nonnoise.items(), key=lambda kv: -kv[1])[:n]]

    b_top = top_clusters(baseline_counts, baseline_size, TOP_N)
    i_top = top_clusters(impr_counts, impr_size, TOP_N)

    def matrix(counts, top, totals):
        M = np.zeros((len(FAILURE_MODES), len(top)))
        for i, m in enumerate(FAILURE_MODES):
            for j, c in enumerate(top):
                M[i, j] = counts[c][m] / totals[m]
        return M

    Mb = matrix(baseline_counts, b_top, totals)
    Mi = matrix(impr_counts, i_top, totals)

    vmax = max(Mb.max(), Mi.max())

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, M, top, title in [
        (axes[0], Mb, b_top, f"Baseline pipeline — top-{TOP_N} clusters by size"),
        (axes[1], Mi, i_top, f"Improved pipeline — top-{TOP_N} clusters by size"),
    ]:
        im = ax.imshow(M, aspect="auto", cmap="viridis", vmin=0, vmax=vmax)
        ax.set_xticks(range(len(top)))
        ax.set_xticklabels([str(c) for c in top], rotation=0)
        ax.set_yticks(range(len(FAILURE_MODES)))
        ax.set_yticklabels([SHORT[m] for m in FAILURE_MODES])
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("cluster id")
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                v = M[i, j]
                if v > 0.02:
                    color = "white" if v < vmax * 0.5 else "black"
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            color=color, fontsize=8)
    fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02,
                 label="recall (fraction of mode's traces in this cluster)")
    fig.suptitle("Cluster × failure-mode recall: baseline vs improved", fontsize=12)
    out = OUT / "cluster_failure_matrix.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


def cluster_116_composition():
    labels = ["sub_reroute", "drift", "esc_loop", "noise", "CSK", "stale_quote"]
    values = [157, 125, 100, 16, 5, 9]
    colors = ["#4C72B0", "#DD8452", "#55A467", "#C44E52", "#8172B2", "#937860"]

    fig, ax = plt.subplots(figsize=(9, 2.6))
    left = 0
    for v, lab, col in zip(values, labels, colors):
        ax.barh([0], [v], left=left, color=col, edgecolor="white", label=f"{lab} ({v})")
        if v >= 10:
            ax.text(left + v / 2, 0, f"{lab}\n{v}", ha="center", va="center",
                    color="white", fontsize=9, fontweight="bold")
        left += v
    ax.set_xlim(0, sum(values))
    ax.set_yticks([])
    ax.set_xlabel("trace count")
    ax.set_title(
        f"Cluster 116 composition (n={sum(values)}): three failure classes co-cluster"
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=6, fontsize=8,
              frameon=False)
    out = OUT / "cluster_116_composition.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    cluster_failure_matrix()
    cluster_116_composition()
