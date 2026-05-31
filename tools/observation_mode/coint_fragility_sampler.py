#!/usr/bin/env python3
"""
B1 — No-notional observation mode: universal coint-fragility sampler.

Authorized 2026-05-31 as exp_beta_aware_sizing_v1 structural-review follow-on.
Answers two questions the halt's eligible-return discriminator cannot
(because the halt stopped producing eligible trades):

  1. TEMPORAL vs STRUCTURAL fragility — does the universe's coint-failure
     rate vary across time (regime change), or has it been steady (always
     this fragile)?
  2. RISK_OFF vector test at N — does coint-failure rate condition on
     entry regime?

Method: read existing bot logs and treat every COINT_GATE event (emitted
~once per minute by the live monitoring loop on the active pair) as a
fragility sample. health ∈ {valid, watch, broken}; fragility = !valid.
This is sampling, not trading — no PnL is computed, no orders are placed,
no marking-fidelity wall applies (query-3's terminal finding doesn't reach
here because the metric is the cointegration test result itself, not a
hypothetical position's pnl).

Pattern precedent: tools/fidelity_validator/validator.py — read-only Python
sidecar, parses bot logs, writes to its own output dir.

Stop-and-report guardrails:
- This script does NOT write to bot-owned files.
- It does NOT invoke any trade-permissioned credentials.
- It does NOT call any bot code or modify bot state.
- It does NOT subscribe to OKX or any live API.
- It reads existing log files only.

Usage:
  Analyze a single run:
      python tools/observation_mode/coint_fragility_sampler.py --run run_142
  Analyze all exp_beta_aware_sizing_v1 runs (125–142):
      python tools/observation_mode/coint_fragility_sampler.py --exp-beta-aware-sizing
  Analyze every run found under Logs/v1/:
      python tools/observation_mode/coint_fragility_sampler.py --all
  Custom run set:
      python tools/observation_mode/coint_fragility_sampler.py --runs run_140 run_141 run_142

Output:
  tools/observation_mode/output/<run_name>__samples.csv  (per-event rows)
  tools/observation_mode/output/summary.csv              (per-run aggregates)
  stdout summary report with TEMPORAL + RISK_OFF reads
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "Logs" / "v1"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


COINT_GATE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+"
    r"COINT_GATE:\s+strategy=(?P<strategy>\S+)\s+coint_flag=(?P<coint_flag>\d+)\s+"
    r"allow_new=(?P<allow_new>\d+)\s+mode=(?P<mode>\S+)\s+"
    r"health=(?P<health>\S+)\s+reason=(?P<reason>\S+)\s+"
    r"p=(?P<p>[\d.e+-]+|nan)\s+adf_gap=(?P<adf_gap>[\d.e+-]+|nan)\s+"
    r"basis=(?P<basis>\S+)\s+sample=(?P<sample>\d+)\s+window=(?P<window>\d+)\s+"
    r"entry_basis=(?P<entry_basis>\S+)\s+entry_coint=(?P<entry_coint>\d+)\s+"
    r"entry_health=(?P<entry_health>\S+)"
)
REGIME_STATUS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+"
    r"REGIME_STATUS:\s+mode=(?P<mode>\S+)\s+regime=(?P<regime>\S+)\s+"
    r"candidate=(?P<candidate>\S+)\s+conf=(?P<conf>[\d.]+)\s+"
    r"trend=(?P<trend>[\d.]+)\s+vol_pct=(?P<vol_pct>[\d.]+)\s+"
    r"depth=(?P<depth>[\d.]+)\s+coint=(?P<coint>\d+)\s+"
    r"fallback=(?P<fallback>\d+)"
)
PAIR_VALIDATED_RE = re.compile(
    r"Ticker configuration validated:\s+ticker_1=(?P<t1>[A-Z0-9-]+),\s+ticker_2=(?P<t2>[A-Z0-9-]+)"
)
PAIR_SWITCH_RE = re.compile(
    r"Switching from (?P<src>[A-Z0-9/-]+) to (?P<dst>[A-Z0-9/-]+)"
)


HEALTH_VALID = "valid"
HEALTH_WATCH = "watch"
HEALTH_BROKEN = "broken"


@dataclass
class Sample:
    ts: str
    pair: str
    regime: str
    vol_pct: float | None
    health: str
    p: float | None
    coint_flag: int
    allow_new: int
    entry_health: str
    mode: str

    @property
    def is_fragile(self) -> bool:
        return self.health != HEALTH_VALID


@dataclass
class RunResult:
    run_name: str
    log_path: Path
    samples: list[Sample] = field(default_factory=list)

    # Aggregates
    n_total: int = 0
    n_valid: int = 0
    n_watch: int = 0
    n_broken: int = 0
    by_regime: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"valid": 0, "watch": 0, "broken": 0}))
    by_pair: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: {"valid": 0, "watch": 0, "broken": 0}))
    start_ts: str | None = None
    end_ts: str | None = None

    @property
    def fragility_rate(self) -> float:
        return (self.n_watch + self.n_broken) / self.n_total if self.n_total else 0.0

    @property
    def broken_rate(self) -> float:
        return self.n_broken / self.n_total if self.n_total else 0.0


def parse_log(log_path: Path, run_name: str) -> RunResult:
    """Single-pass log parser building the run-level sample stream.

    Pair tracking: starts from 'Ticker configuration validated' (initial)
    and updates on each 'Switching from X to Y'. Regime state tracked from
    the most recent REGIME_STATUS line.
    """
    result = RunResult(run_name=run_name, log_path=log_path)
    current_pair = "unknown"
    current_regime = "unknown"
    current_vol_pct: float | None = None

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Pair tracking
            pv = PAIR_VALIDATED_RE.search(line)
            if pv:
                current_pair = f"{pv.group('t1')}/{pv.group('t2')}"
                continue
            ps = PAIR_SWITCH_RE.search(line)
            if ps:
                current_pair = ps.group("dst")
                continue

            # Regime tracking
            rm = REGIME_STATUS_RE.match(line)
            if rm:
                current_regime = rm.group("regime")
                try:
                    current_vol_pct = float(rm.group("vol_pct"))
                except ValueError:
                    current_vol_pct = None
                continue

            # COINT_GATE samples (the core data)
            cg = COINT_GATE_RE.match(line)
            if not cg:
                continue
            try:
                p_val = float(cg.group("p"))
            except ValueError:
                p_val = None
            s = Sample(
                ts=cg.group("ts"),
                pair=current_pair,
                regime=current_regime,
                vol_pct=current_vol_pct,
                health=cg.group("health"),
                p=p_val,
                coint_flag=int(cg.group("coint_flag")),
                allow_new=int(cg.group("allow_new")),
                entry_health=cg.group("entry_health"),
                mode=cg.group("mode"),
            )
            result.samples.append(s)

    # Aggregate
    for s in result.samples:
        result.n_total += 1
        if s.health == HEALTH_VALID:
            result.n_valid += 1
        elif s.health == HEALTH_WATCH:
            result.n_watch += 1
        elif s.health == HEALTH_BROKEN:
            result.n_broken += 1
        result.by_regime[s.regime][s.health] = result.by_regime[s.regime].get(s.health, 0) + 1
        result.by_pair[s.pair][s.health] = result.by_pair[s.pair].get(s.health, 0) + 1
    if result.samples:
        result.start_ts = result.samples[0].ts
        result.end_ts = result.samples[-1].ts
    return result


def write_samples_csv(result: RunResult, out_dir: Path) -> Path:
    path = out_dir / f"{result.run_name}__samples.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp", "pair", "regime", "vol_pct", "health", "p_value",
            "coint_flag", "allow_new", "entry_health", "mode", "is_fragile",
        ])
        for s in result.samples:
            w.writerow([
                s.ts, s.pair, s.regime,
                f"{s.vol_pct:.3f}" if s.vol_pct is not None else "",
                s.health,
                f"{s.p:.4f}" if s.p is not None else "",
                s.coint_flag, s.allow_new, s.entry_health, s.mode,
                int(s.is_fragile),
            ])
    return path


def write_summary_csv(results: list[RunResult], out_dir: Path) -> Path:
    path = out_dir / "summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "run", "start_ts", "end_ts", "n_total",
            "n_valid", "n_watch", "n_broken",
            "fragility_rate", "broken_rate",
            "n_RANGE", "broken_RANGE", "broken_rate_RANGE",
            "n_RISK_OFF", "broken_RISK_OFF", "broken_rate_RISK_OFF",
            "n_TREND", "broken_TREND", "broken_rate_TREND",
        ])
        for r in results:
            def regime_stats(reg: str) -> tuple[int, int, str]:
                d = r.by_regime.get(reg, {})
                n = sum(d.values())
                br = d.get("broken", 0)
                rate = f"{br / n:.4f}" if n else ""
                return (n, br, rate)
            nr, br_r, rr = regime_stats("RANGE")
            no, br_o, ro = regime_stats("RISK_OFF")
            nt, br_t, rt = regime_stats("TREND")
            w.writerow([
                r.run_name, r.start_ts or "", r.end_ts or "", r.n_total,
                r.n_valid, r.n_watch, r.n_broken,
                f"{r.fragility_rate:.4f}", f"{r.broken_rate:.4f}",
                nr, br_r, rr,
                no, br_o, ro,
                nt, br_t, rt,
            ])
    return path


def discover_run_logs(run_names: Iterable[str]) -> list[tuple[str, Path]]:
    """Map run names (e.g. 'run_142') to their (canonical_name, log_path)."""
    found: list[tuple[str, Path]] = []
    for name in run_names:
        prefix = name if name.startswith("run_") else f"run_{name}"
        matches = sorted(LOGS_DIR.glob(f"{prefix}_*"))
        if not matches:
            print(f"  WARN: no log dir matching {prefix}_* under {LOGS_DIR}", file=sys.stderr)
            continue
        run_dir = matches[0]
        log_files = list(run_dir.glob("log_*.log"))
        if not log_files:
            print(f"  WARN: no log file in {run_dir}", file=sys.stderr)
            continue
        found.append((run_dir.name, log_files[0]))
    return found


def discover_all_runs() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for run_dir in sorted(LOGS_DIR.glob("run_*")):
        log_files = list(run_dir.glob("log_*.log"))
        if log_files:
            out.append((run_dir.name, log_files[0]))
    return out


EXP_BETA_RUN_NUMBERS = list(range(125, 143))  # 125..142 inclusive


def print_run_report(r: RunResult) -> None:
    print(f"\n--- {r.run_name} ---")
    print(f"  window: {r.start_ts} -> {r.end_ts}")
    print(f"  n_total={r.n_total}  valid={r.n_valid}  watch={r.n_watch}  broken={r.n_broken}")
    print(f"  fragility_rate (watch+broken)/total = {r.fragility_rate:.4f}")
    print(f"  broken_rate                          = {r.broken_rate:.4f}")
    if r.by_regime:
        print("  by regime:")
        for reg, d in sorted(r.by_regime.items()):
            n = sum(d.values())
            frag = (d.get("watch", 0) + d.get("broken", 0)) / n if n else 0.0
            print(f"    {reg:<10} n={n:>5}  frag={frag:.4f}  (valid={d.get('valid',0)} watch={d.get('watch',0)} broken={d.get('broken',0)})")


def print_aggregate_report(results: list[RunResult]) -> None:
    if not results:
        return
    print("\n=== AGGREGATE (all analyzed runs) ===")
    total = sum(r.n_total for r in results)
    valid = sum(r.n_valid for r in results)
    watch = sum(r.n_watch for r in results)
    broken = sum(r.n_broken for r in results)
    if total == 0:
        print("  no COINT_GATE samples found")
        return
    print(f"  n_total={total}  valid={valid}  watch={watch}  broken={broken}")
    print(f"  fragility_rate = {(watch + broken) / total:.4f}")
    print(f"  broken_rate    = {broken / total:.4f}")

    # Cross-regime aggregate
    by_regime: dict[str, dict[str, int]] = defaultdict(lambda: {"valid": 0, "watch": 0, "broken": 0})
    for r in results:
        for reg, d in r.by_regime.items():
            for k, v in d.items():
                by_regime[reg][k] = by_regime[reg].get(k, 0) + v
    print("\n  by regime (RISK_OFF vector test):")
    for reg, d in sorted(by_regime.items()):
        n = sum(d.values())
        frag = (d.get("watch", 0) + d.get("broken", 0)) / n if n else 0.0
        print(f"    {reg:<10} n={n:>6}  frag={frag:.4f}  (valid={d.get('valid',0)} watch={d.get('watch',0)} broken={d.get('broken',0)})")

    # Temporal arc (per-run sequence)
    print("\n  per-run sequence (TEMPORAL vs STRUCTURAL discriminator):")
    print(f"    {'run':<32} {'n':>6} {'frag':>7} {'broken':>7}")
    for r in results:
        print(f"    {r.run_name:<32} {r.n_total:>6} {r.fragility_rate:>7.4f} {r.broken_rate:>7.4f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="B1 — no-notional coint-fragility sampler")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", help="single run name (e.g. run_142)")
    g.add_argument("--runs", nargs="+", help="explicit run names")
    g.add_argument("--exp-beta-aware-sizing", action="store_true",
                   help="analyze runs 125..142 (exp_beta_aware_sizing_v1 window)")
    g.add_argument("--all", action="store_true", help="analyze every run under Logs/v1")
    ap.add_argument("--no-per-run-csv", action="store_true",
                    help="skip writing per-run sample CSVs (still writes summary.csv)")
    args = ap.parse_args(argv)

    if args.run:
        targets = discover_run_logs([args.run])
    elif args.runs:
        targets = discover_run_logs(args.runs)
    elif args.exp_beta_aware_sizing:
        targets = discover_run_logs([f"run_{n}" for n in EXP_BETA_RUN_NUMBERS])
    else:
        targets = discover_all_runs()

    if not targets:
        print("ERR: no run logs found", file=sys.stderr)
        return 1

    results: list[RunResult] = []
    for run_name, log_path in targets:
        print(f"parsing {run_name} ({log_path.name}) ...", flush=True)
        r = parse_log(log_path, run_name)
        if not args.no_per_run_csv:
            csv_path = write_samples_csv(r, OUTPUT_DIR)
            print(f"  -> {csv_path.relative_to(PROJECT_ROOT)}")
        print_run_report(r)
        results.append(r)

    summary_path = write_summary_csv(results, OUTPUT_DIR)
    print(f"\nsummary: {summary_path.relative_to(PROJECT_ROOT)}")
    print_aggregate_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
