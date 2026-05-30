# Section-5 Path-1 Fidelity-Gate Validator

Sidecar implementation of the query-3 spec v1.2 §5 marking-fidelity gate
(Path 1 — LIVE concurrent verification).

## What it does

Subscribes to OKX public WS `mark-price` for the currently-open trade's
instruments. On every `position_snapshots.csv` row the live bot writes, it
computes `virtual_pnl = L_cap × (L_mark/L_entry − 1) − S_cap × (S_mark/S_entry − 1)`
using the live marks at that moment, and compares to the bot's recorded
`unrealized_pnl_usdt`.

The output CSV records every comparison: `recorded_pnl`, `virtual_pnl`,
`diff`, `abs_diff`, and `within_cent` (yes/no).

## Pass criterion (per spec v1.2 §5)

**≥ 99% of compared ticks within $0.01, over ≥ 3 live trades' full snapshot
series.** The ≤1% out-of-tolerance bucket must be randomly distributed
(not clustered at trade open/close, by side, or by pair) — clustering
indicates a formula bug regardless of bulk pass rate.

## Read-only / non-perturbing guarantees

- No writes to bot-owned files (logs, snapshots, state).
- No trade-permissioned credentials. WS subscription is public, no auth.
- No bot code modification (Path A: parses bot log + tails snapshot CSV).
- No REST polling that shares rate-limit with the bot's trading path.
- Runs as a separate process — bot timing, state, credentials untouched.

## Stop-and-report triggers

If any of these surface during operation, **stop and report** rather than
extending into the harness:

- A need to modify any file under `Execution/`, `Strategy/`, or `Platform/`.
- The WS `mark-price` stream not matching OKX's internal mark used for
  unrealized PnL (consistent non-trivial diffs after several trades).
- Any contention with the live bot's execution path.

## Usage

```bash
# Start AFTER a live run begins (i.e., once Reports/v1/run_N/
# position_snapshots.csv exists for the active run):
python tools/fidelity_validator/validator.py
```

Output: `tools/fidelity_validator/logs/fidelity_<run_name>.csv`

**If a new run starts, kill the validator (Ctrl+C) and restart it.**
The validator auto-detects the *latest* run dir at startup and is
intentionally pinned to it for the session.

## Dependencies

- Python 3.8+
- `websockets` (Python lib) — already present in the project env.

## Aggregating across runs

After 3+ runs have been validated, compute the pass rate from the union
of per-run output CSVs:

```python
import csv, glob
total = within = 0
for f in glob.glob("tools/fidelity_validator/logs/fidelity_run_*.csv"):
    for row in csv.DictReader(open(f)):
        total += 1
        if row["within_cent"] == "yes":
            within += 1
print(f"{within}/{total} = {within/total*100:.1f}% within $0.01")
```

Pass if ≥ 99% AND the failures are randomly distributed (not clustered).

## Path A vs Path B

This implementation uses **Path A** (parses bot log for entry info; zero
bot code change). If the log-format dependency turns out brittle in
practice, Path B (a one-line bot logging addition to a dedicated state
file) is the fallback — requires a separate operator authorization, not
implemented here.

## V1 scope notes

This is a feasibility-test implementation. Known V1 limitations to
revisit if the gate passes and we want a production-grade validator:

- No automatic detection of a new run (restart manually on run change).
- No graceful re-bind after the run dir changes mid-process.
- Errors are logged to stdout but the script keeps running; check the
  output CSV for completeness rather than relying on stdout.
- The mark-price WS subscription is incremental (subscribes to new
  instruments as new trades open) but does NOT unsubscribe stale ones —
  harmless, just slightly higher message volume in long sessions.
