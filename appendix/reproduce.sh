#!/usr/bin/env bash
# Reproduce every number in article.md from a clean checkout.
# Target wall time: < 5 minutes on a CPU-only laptop.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "[1/6] Generating synthetic traces (5,000 traces, seed 42, ~5s)..."
python3 sim/generate_traces.py

echo "[2/6] Running baseline pipeline (~30s)..."
python3 baseline/pipeline.py

echo "[3/6] Running improved pipeline (~30s)..."
python3 improved/pipeline.py

if [ -f baseline_handfeature/pipeline.py ]; then
  echo "[4/6] Running hand-feature baseline (~10s)..."
  python3 baseline_handfeature/pipeline.py
else
  echo "[4/6] Hand-feature baseline not yet present, skipping."
fi

echo "[5/6] Computing metrics with bootstrap CIs (~20s)..."
python3 eval/metrics.py

if [ -f eval/cluster_stability.py ]; then
  echo "[6/6] HDBSCAN min_cluster_size perturbation (~2min)..."
  python3 eval/cluster_stability.py
else
  echo "[6/6] Cluster stability check not yet present, skipping."
fi

echo
echo "Reproduction complete. Compare numbers in article.md against eval/raw_numbers.json:"
echo "  diff <(grep -oE '[0-9]+\\.[0-9]+' article.md | sort -u) \\"
echo "       <(python3 -c \"import json; [print(n) for n in sorted(set(map(str, [v for v in json.load(open('eval/raw_numbers.json'), object_hook=lambda d: list(d.values()) ) if isinstance(v, (int, float))])))]\")"
echo
echo "Pre-registration: eval/preregistration.md"
echo "Verdicts:         eval/results.md"
echo "Provenance check: eval/provenance_check.md (if present)"
echo "Adversarial review summary: meta/convergence.md"
