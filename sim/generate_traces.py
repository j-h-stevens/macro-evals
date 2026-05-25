"""Synthetic EV-order post-configuration agent-trace generator.

Produces 5000 traces across 90 simulated days with ground-truth failure-mode
labels. Pure stdlib, deterministic under seed=42. See SCHEMA.md for the
field-by-field contract.

Design notes / judgment calls:
- We separate the *injection* of a failure mode from the *manifestation* in
  events, so the labels are unambiguous ground truth. A trace is labelled
  with mode X iff we deliberately chose to inject mode X.
- `pricing_drift` is a *population* failure (post-day-45) and is labelled on
  every post-45 trace that actually contains a pricing return. Detection of
  this mode requires aggregation; no single trace looks broken.
- Tariff/substitution correlation is achieved via a hidden `import_heavy`
  SKU flag that *both* raises tariff probability and substitution
  probability. Tariffs themselves do not cause substitutions.
- Random-noise failures get the `random_noise_failure` label so the
  HDBSCAN-noise hypothesis is testable downstream.
- Confounders (latency spikes, retries, prompt-version wording shift at
  day 60) are deliberately NOT labelled — they should be ignored by a
  well-built pipeline.
"""

from __future__ import annotations

import json
import os
import random
from collections import Counter, defaultdict
from typing import Any

SEED = 42
N_TRACES = 5000
N_DAYS = 90
DRIFT_DAY = 45
PROMPT_VERSION_DAY = 60
PRICING_DRIFT_BIAS = 0.004  # +0.4%

OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "traces.jsonl")

AGENTS = ["orchestrator", "pricing", "compliance", "supply",
          "factory", "scheduling", "release"]

CASE_TYPES = [
    "standard_build",
    "supplier_substitution",
    "regulated_export",
    "expedited_delivery",
    "custom_configuration",
]

# Prompt-version cosmetic wording shift at day 60 — surface only, no semantics.
WORDING = {
    "v1": {"ok": "ok", "quote": "quote_ready", "release": "release_ok"},
    "v2": {"ok": "acknowledged", "quote": "quote_prepared", "release": "released"},
}


def day_volume_curve(day: int) -> float:
    """Seasonal volume: ~30% rise across the 90 days, smooth ramp."""
    return 1.0 + 0.30 * (day / (N_DAYS - 1))


def assign_days(rng: random.Random, n: int) -> list[int]:
    """Distribute n traces across days weighted by the seasonal curve."""
    weights = [day_volume_curve(d) for d in range(N_DAYS)]
    total = sum(weights)
    # Expected count per day, then top-up with rng to hit exactly n.
    counts = [int(round(n * w / total)) for w in weights]
    # Fix off-by-one drift
    diff = n - sum(counts)
    while diff != 0:
        idx = rng.randrange(N_DAYS)
        if diff > 0:
            counts[idx] += 1
            diff -= 1
        elif counts[idx] > 0:
            counts[idx] -= 1
            diff += 1
    days = []
    for d, c in enumerate(counts):
        days.extend([d] * c)
    rng.shuffle(days)
    return days


def mk_event(t_ms: int, agent: str, ev_type: str, *,
             to: str | None = None, tool: str | None = None,
             args: dict | None = None, latency_ms: int = 0,
             env_signals: list[str] | None = None,
             value: Any = None, note: str | None = None) -> dict:
    e = {"t_ms": t_ms, "agent": agent, "type": ev_type, "latency_ms": latency_ms}
    if to is not None:
        e["to"] = to
    if tool is not None:
        e["tool"] = tool
    if args is not None:
        e["args"] = args
    if env_signals:
        e["env_signals"] = env_signals
    if value is not None:
        e["value"] = value
    if note is not None:
        e["note"] = note
    return e


def base_price(rng: random.Random) -> float:
    return round(rng.uniform(38000, 92000), 2)


def build_trace(rng: random.Random, trace_idx: int, day: int) -> dict:
    """Build one trace. Decides case type, injects failure modes, returns dict."""
    # Hidden confounder: import-heavy SKU. Drives BOTH tariff and substitution
    # WITHOUT either causing the other. We tune the conditional probs so the
    # observed phi correlation hits ~0.4.
    import_heavy = rng.random() < 0.15

    # Tariff: very rare for domestic, very common for import-heavy.
    tariff = rng.random() < (0.06 if not import_heavy else 0.78)

    # Substitution: rare for domestic, common for import-heavy.
    sub_inject = rng.random() < (0.022 if not import_heavy else 0.38)

    # Other failure injections (independent draws). Tuned so overall rate ~5%.
    compliance_skip_inject = tariff and (rng.random() < 0.27)
    stale_quote_inject = rng.random() < 0.04
    escalation_loop_inject = rng.random() < 0.036
    noise_failure_inject = rng.random() < 0.06
    minor_noise = rng.random() < 0.15  # unlabelled confounder

    prompt_version = "v2" if day >= PROMPT_VERSION_DAY else "v1"
    w = WORDING[prompt_version]

    # Pick case type. Substitution forces the substitution case_type.
    if sub_inject:
        case_type = "supplier_substitution"
    else:
        case_type = rng.choices(
            CASE_TYPES,
            weights=[0.45, 0.05, 0.15, 0.20, 0.15],  # subs base is low; injection lifts it
        )[0]

    env_signals: list[str] = []
    if tariff:
        env_signals.append("tariff_us_eu")
    if import_heavy:
        env_signals.append("import_heavy_sku")
    if case_type == "expedited_delivery":
        env_signals.append("expedite_flag")
    if rng.random() < 0.08:
        env_signals.append("low_stock_warn")

    events: list[dict] = []
    t = 0
    failure_modes: list[str] = []

    # 1. Orchestrator opens the case.
    events.append(mk_event(t, "orchestrator", "call", to="pricing",
                           tool="request_quote",
                           args={"sku_class": "import" if import_heavy else "domestic"},
                           latency_ms=rng.randint(40, 180),
                           env_signals=env_signals or None))
    t += events[-1]["latency_ms"]

    # 2. Pricing returns. Latency, drift, stale-quote logic live here.
    pricing_latency = rng.randint(180, 900)
    if stale_quote_inject:
        pricing_latency = rng.randint(3100, 6200)
        failure_modes.append("stale_quote_slow_pricing")

    raw_price = base_price(rng)
    drift_applied = day >= DRIFT_DAY
    price = round(raw_price * (1.0 + PRICING_DRIFT_BIAS), 2) if drift_applied \
        else round(raw_price, 2)

    pv = {"price_usd": price, "status": w["quote"]}
    # Hidden raw price (debug-only field, prefixed with _) — used for paired
    # drift verification. Detectors should ignore underscore-prefixed fields.
    pv["_raw_price_usd"] = round(raw_price, 2)
    events.append(mk_event(t, "pricing", "return", to="orchestrator",
                           tool="request_quote",
                           value=pv,
                           latency_ms=pricing_latency))
    t += pricing_latency

    if drift_applied:
        # Population-level label: every post-45 trace with a real pricing return.
        failure_modes.append("pricing_drift")

    # 3. Compliance call — UNLESS we're injecting the omission failure.
    if compliance_skip_inject:
        failure_modes.append("compliance_skipped_under_tariff")
        # The expected compliance call is absent. We still leave a note-free gap.
    else:
        events.append(mk_event(t, "orchestrator", "call", to="compliance",
                               tool="check_regs",
                               args={"jurisdiction": "EU" if tariff else "US"},
                               latency_ms=rng.randint(60, 220)))
        t += events[-1]["latency_ms"]
        comp_lat = rng.randint(150, 700)
        comp_status = "pass" if rng.random() < 0.92 else "review"
        events.append(mk_event(t, "compliance", "return", to="orchestrator",
                               tool="check_regs",
                               value={"status": comp_status},
                               latency_ms=comp_lat))
        t += comp_lat

    # 4. Supply check.
    events.append(mk_event(t, "orchestrator", "call", to="supply",
                           tool="check_stock", latency_ms=rng.randint(50, 200)))
    t += events[-1]["latency_ms"]

    sub_value: dict
    if sub_inject:
        sub_value = {"status": "substitute", "alt_part": f"ALT-{rng.randint(1000,9999)}"}
        failure_modes.append("substitution_reroute")
    else:
        sub_value = {"status": "in_stock"}
    sup_lat = rng.randint(120, 500)
    events.append(mk_event(t, "supply", "return", to="orchestrator",
                           tool="check_stock", value=sub_value,
                           latency_ms=sup_lat))
    t += sup_lat

    # 5. If substitution → factory reroute path.
    if sub_inject:
        events.append(mk_event(t, "orchestrator", "handoff", to="factory",
                               note="reroute_for_substitute",
                               latency_ms=rng.randint(20, 80)))
        t += events[-1]["latency_ms"]
        fact_lat = rng.randint(200, 900)
        events.append(mk_event(t, "factory", "return", to="orchestrator",
                               tool="reroute_build",
                               value={"status": "rerouted",
                                      "alt_part": sub_value["alt_part"]},
                               latency_ms=fact_lat))
        t += fact_lat

    # 6. Scheduling.
    events.append(mk_event(t, "orchestrator", "call", to="scheduling",
                           tool="slot", latency_ms=rng.randint(40, 160)))
    t += events[-1]["latency_ms"]
    sch_lat = rng.randint(150, 500)
    events.append(mk_event(t, "scheduling", "return", to="orchestrator",
                           tool="slot",
                           value={"slot_day": day + rng.randint(2, 9)},
                           latency_ms=sch_lat))
    t += sch_lat

    # 7. Release — possibly with escalation loop.
    loop_iters = 1
    if escalation_loop_inject:
        loop_iters = rng.randint(2, 4)
        failure_modes.append("escalation_loop")
    for i in range(loop_iters):
        events.append(mk_event(t, "orchestrator", "call", to="release",
                               tool="release_order",
                               latency_ms=rng.randint(30, 120)))
        t += events[-1]["latency_ms"]
        rel_lat = rng.randint(100, 400)
        if i < loop_iters - 1:
            # Release bounces back to compliance.
            events.append(mk_event(t, "release", "return", to="orchestrator",
                                   tool="release_order",
                                   value={"status": "needs_review"},
                                   latency_ms=rel_lat))
            t += rel_lat
            events.append(mk_event(t, "orchestrator", "call", to="compliance",
                                   tool="recheck_regs",
                                   latency_ms=rng.randint(40, 120)))
            t += events[-1]["latency_ms"]
            rec_lat = rng.randint(120, 400)
            events.append(mk_event(t, "compliance", "return", to="orchestrator",
                                   tool="recheck_regs",
                                   value={"status": "review"},
                                   latency_ms=rec_lat))
            t += rec_lat
        else:
            events.append(mk_event(t, "release", "return", to="orchestrator",
                                   tool="release_order",
                                   value={"status": w["release"]},
                                   latency_ms=rel_lat))
            t += rel_lat

    # 8. Confounder: minor unlabelled noise (latency spike or retry).
    if minor_noise:
        if rng.random() < 0.5:
            # latency spike on a random in-trace event
            tgt = rng.choice(events)
            tgt["latency_ms"] += rng.randint(400, 1200)
            t += 0  # already past; we just inflate one stat
        else:
            # retried tool call
            events.append(mk_event(t, "scheduling", "tool", tool="slot_retry",
                                   latency_ms=rng.randint(80, 250),
                                   note="transient_retry"))
            t += events[-1]["latency_ms"]

    # 9. Random noise failure (labelled; should look unrelated).
    if noise_failure_inject:
        failure_modes.append("random_noise_failure")
        weird_agent = rng.choice(AGENTS)
        events.append(mk_event(t, weird_agent, "signal",
                               note=rng.choice([
                                   "unexpected_log_emit",
                                   "metric_blip_unrelated",
                                   "telemetry_drop",
                                   "spurious_warning",
                               ]),
                               latency_ms=rng.randint(5, 40)))
        t += events[-1]["latency_ms"]

    # Outcome derivation.
    if escalation_loop_inject:
        outcome = "review"
    elif compliance_skip_inject and tariff:
        outcome = "completed"  # silently bad — that's the point of the omission
    elif noise_failure_inject and rng.random() < 0.15:
        outcome = "failed"
    elif sub_inject:
        outcome = "completed"
    elif stale_quote_inject and rng.random() < 0.25:
        outcome = "review"
    else:
        outcome = "completed" if rng.random() < 0.93 else "review"

    return {
        "trace_id": f"t{trace_idx:05d}",
        "day": day,
        "case_type": case_type,
        "events": events,
        "env_signals": env_signals,
        "outcome": outcome,
        "failure_modes": failure_modes,
        "prompt_version": prompt_version,
    }


def validate_and_summarize(traces: list[dict]) -> None:
    n = len(traces)
    assert n == N_TRACES, f"expected {N_TRACES} traces, got {n}"

    mode_counts: Counter = Counter()
    case_counts: Counter = Counter()
    day_counts: Counter = Counter()
    cooc: dict[tuple[str, str], int] = defaultdict(int)
    prompt_counts: Counter = Counter()
    outcome_counts: Counter = Counter()

    # Drift verification: paired ratios (drifted / raw) post-day-45 should
    # all equal exactly 1 + PRICING_DRIFT_BIAS; pre should equal 1.0.
    pricing_pre, pricing_post = [], []
    drift_ratios_post, drift_ratios_pre = [], []
    drift_violations = 0
    sub_and_tariff = 0
    sub_total = 0
    tariff_total = 0

    for tr in traces:
        case_counts[tr["case_type"]] += 1
        day_counts[tr["day"]] += 1
        prompt_counts[tr["prompt_version"]] += 1
        outcome_counts[tr["outcome"]] += 1
        modes = tr["failure_modes"]
        for m in modes:
            mode_counts[m] += 1
        for i, a in enumerate(modes):
            for b in modes[i + 1:]:
                key = tuple(sorted((a, b)))
                cooc[key] += 1

        has_tariff = "tariff_us_eu" in tr["env_signals"]
        has_sub = "substitution_reroute" in modes
        if has_tariff:
            tariff_total += 1
        if has_sub:
            sub_total += 1
        if has_tariff and has_sub:
            sub_and_tariff += 1

        for ev in tr["events"]:
            if ev["agent"] == "pricing" and ev["type"] == "return" \
                    and isinstance(ev.get("value"), dict) \
                    and "price_usd" in ev["value"]:
                p = ev["value"]["price_usd"]
                raw = ev["value"].get("_raw_price_usd", p)
                ratio = p / raw if raw else 1.0
                if tr["day"] >= DRIFT_DAY:
                    pricing_post.append(p)
                    drift_ratios_post.append(ratio)
                    if abs(ratio - (1.0 + PRICING_DRIFT_BIAS)) > 1e-4:
                        drift_violations += 1
                else:
                    pricing_pre.append(p)
                    drift_ratios_pre.append(ratio)
                    if abs(ratio - 1.0) > 1e-4:
                        drift_violations += 1

    # Day span check
    assert min(day_counts) == 0 and max(day_counts) == N_DAYS - 1, \
        "day span must cover 0..89"

    # Paired drift verification using raw vs drifted within each post-day-45
    # pricing event: this isolates the bias from sampling noise.
    pre_mean = sum(pricing_pre) / len(pricing_pre)
    post_mean = sum(pricing_post) / len(pricing_post)
    post_ratio_mean = sum(drift_ratios_post) / len(drift_ratios_post)
    pre_ratio_mean = sum(drift_ratios_pre) / len(drift_ratios_pre)
    assert drift_violations == 0, \
        f"drift integrity broken on {drift_violations} pricing events"

    # Prevalence spec
    spec = {
        "substitution_reroute": 0.08,
        "compliance_skipped_under_tariff": 0.05,
        "stale_quote_slow_pricing": 0.04,
        "escalation_loop": 0.03,
        "random_noise_failure": 0.06,
    }

    print("=" * 64)
    print(f"Generated {n} traces, span days {min(day_counts)}..{max(day_counts)}")
    print(f"Prompt versions: {dict(prompt_counts)}")
    print(f"Outcomes: {dict(outcome_counts)}")
    print()
    print("Case types:")
    for c, k in case_counts.most_common():
        print(f"  {c:30s} {k:5d}  ({k/n:.1%})")
    print()
    print("Failure modes (count, prevalence, spec, delta):")
    for m, target in spec.items():
        actual = mode_counts[m] / n
        flag = "OK" if abs(actual - target) <= 0.005 else "CHECK"
        print(f"  {m:36s} {mode_counts[m]:5d}  {actual:.3%}  "
              f"(spec {target:.1%})  [{flag}]")
    pd_count = mode_counts["pricing_drift"]
    post45_traces = sum(1 for tr in traces if tr["day"] >= DRIFT_DAY)
    print(f"  {'pricing_drift':36s} {pd_count:5d}  {pd_count/n:.3%}  "
          f"(spec 100% post-day-{DRIFT_DAY}; post-45 traces = {post45_traces})")
    print()
    print("Confounder check — tariff↔substitution correlation:")
    print(f"  P(sub) = {sub_total/n:.3%}, P(tariff) = {tariff_total/n:.3%}")
    print(f"  P(sub & tariff) = {sub_and_tariff/n:.3%}, "
          f"P(sub|tariff) = {sub_and_tariff/max(tariff_total,1):.3%}")
    # crude phi-like correlation
    p_s, p_t = sub_total/n, tariff_total/n
    p_st = sub_and_tariff/n
    denom = (p_s*(1-p_s)*p_t*(1-p_t)) ** 0.5
    phi = (p_st - p_s*p_t) / denom if denom else 0
    print(f"  phi(tariff, substitution) ≈ {phi:.3f}  (target ~0.4)")
    print()
    print("Drift check (paired ratio drifted/raw per pricing event):")
    print(f"  pre-day-{DRIFT_DAY}  ratio mean = {pre_ratio_mean:.6f}  "
          f"(n={len(drift_ratios_pre)}, expect 1.000000)")
    print(f"  post-day-{DRIFT_DAY} ratio mean = {post_ratio_mean:.6f}  "
          f"(n={len(drift_ratios_post)}, expect {1+PRICING_DRIFT_BIAS:.6f})")
    print(f"  drift integrity violations: {drift_violations}")
    print(f"  unpaired pre mean ${pre_mean:,.2f}  vs post mean ${post_mean:,.2f} "
          f"(swamped by SKU variance — paired view is the truth)")
    print()
    print("Failure-mode co-occurrence (pairs that ever appear together):")
    for (a, b), k in sorted(cooc.items(), key=lambda x: -x[1]):
        print(f"  {a:36s} + {b:32s} {k:4d}")
    print("=" * 64)


def main() -> None:
    rng = random.Random(SEED)
    days = assign_days(rng, N_TRACES)
    traces: list[dict] = []
    for i, d in enumerate(days):
        traces.append(build_trace(rng, i, d))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as fh:
        for tr in traces:
            fh.write(json.dumps(tr, separators=(",", ":")) + "\n")

    validate_and_summarize(traces)
    print(f"\nWrote {len(traces)} traces to {OUT_PATH}")


if __name__ == "__main__":
    main()
