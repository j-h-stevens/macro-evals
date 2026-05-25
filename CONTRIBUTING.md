# Contributing

This repository is the published artifact of a pre-registered audit. The article in `article.md` makes falsifiable claims and the most useful way to engage is to test one of them.

## Five ways to contribute

### 1. Run a dated falsifier and PR the result

Each of the five falsifiers in `article.md` §"Five dated falsifiers" names a specific experiment with a date. If you run one and it flips the verdict, PR with:

- Your run script
- The output artifacts (cluster_x_failure_mode.csv equivalents)
- A one-paragraph summary
- A diff against `article.md` updating the affected claim

We will accept the PR (with attribution), or open a counter-issue with our objection.

### 2. Add a topology to the synthetic generator

Our `sim/generate_traces.py` hardcodes hub-and-spoke. Multiple panel critiques (Pearl, Shalizi, Carmack) argue the walk-vs-MFA-5 result is topology-conditional. PR a heterarchical, chained-specialist, or mesh topology and re-run the pipelines.

### 3. Swap the embedder

Falsifier #5 names this directly. Replace `sentence-transformers/all-MiniLM-L6-v2` in `baseline/pipeline.py` with another encoder (text-embedding-3-small, bge-large-en-v1.5, jina-embeddings-v3, ColBERT), re-run, PR your results. If the H2 absence-token mechanism survives under any encoder, our §9 claim weakens substantially.

### 4. Run on real production traces

The biggest limitation: we did not run on real production agent traces. If you have a real trace stream (even ~10K traces) and can share aggregate cluster structure, PR a `case-studies/your-org-name.md` with what you find.

### 5. Flag a number that does not match the artifacts

`article.md` ends with: "If you find a number in this article that does not match the artifacts, the artifacts are right and the article is wrong." File an issue, we will fix the article or the test, depending on which is right.

## What we will not merge

- Stylistic edits to the article that change argument structure without evidence (we ran a 60-expert critique pass; further prose polish is welcome, but argument changes need data).
- New "improved" mechanisms that are not pre-registered against a falsifiable hypothesis with a threshold and bootstrap CI.
- Changes that silently delete `meta/`. The adversarial review is part of the artifact.

## Process

```bash
# Fork, branch, run, PR
git checkout -b experiment/your-falsifier-name
# Make changes
bash appendix/reproduce.sh   # must still pass
git commit -m "experiment: <falsifier description>"
gh pr create --fill
```

## Cookbook authors

You are explicitly invited to file issues, PRs, or counter-articles. The audit treats you as the strongest possible counterparty. We have written what we believe to be the strongest defense of your work in `article.md` §"What the cookbook authors will reply"; if our steelman is too weak, please correct it.
