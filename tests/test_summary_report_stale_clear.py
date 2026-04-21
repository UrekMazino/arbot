import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd


os.environ["STATBOT_SKIP_INSTRUMENT_FETCH"] = "1"
os.environ["STATBOT_LOG_PATH"] = os.path.join(tempfile.gettempdir(), "okxstatbot-test-summary-report.log")

ROOT_DIR = Path(__file__).resolve().parents[1]
STRATEGY_DIR = ROOT_DIR / "Strategy"
if str(STRATEGY_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_summary_report as fsr


def test_summary_report_clears_stale_rows_when_no_pairs(monkeypatch, tmp_path):
    monkeypatch.setattr(fsr, "_output_dir", lambda: tmp_path)

    (tmp_path / "1_price_list.json").write_text(json.dumps({}), encoding="utf-8")
    pd.DataFrame(columns=["sym_1", "sym_2"]).to_csv(tmp_path / "2_cointegrated_pairs.csv", index=False)
    stale_report = tmp_path / "4_summary_report.csv"
    stale_report.write_text(
        "generated_at,rank,sym_1,sym_2\n2026-04-21 09:46:36,1,OLD-A,OLD-B\n",
        encoding="utf-8",
    )

    report_path = fsr.generate_summary_report(top_n=3)

    assert report_path
    cleared = pd.read_csv(stale_report)
    assert list(cleared.columns) == fsr.REPORT_COLUMNS
    assert cleared.empty
    assert "OLD-A" not in stale_report.read_text(encoding="utf-8")


def test_summary_report_clears_stale_rows_when_inputs_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(fsr, "_output_dir", lambda: tmp_path)
    stale_report = tmp_path / "4_summary_report.csv"
    stale_report.write_text(
        "generated_at,rank,sym_1,sym_2\n2026-04-21 09:46:36,1,OLD-A,OLD-B\n",
        encoding="utf-8",
    )

    report_path = fsr.generate_summary_report(top_n=3)

    assert report_path
    cleared = pd.read_csv(stale_report)
    assert list(cleared.columns) == fsr.REPORT_COLUMNS
    assert cleared.empty
