"""
Generate CSV summary report with top cointegrated pairs.
"""

from datetime import datetime
from pathlib import Path
import json

import numpy as np
import pandas as pd

from func_strategy_log import get_strategy_logger

from func_cointegration import extract_close_prices, calculate_spread, calculate_zscore

REPORT_COLUMNS = [
    "generated_at",
    "rank",
    "sym_1",
    "sym_2",
    "zero_crossings",
    "p_value",
    "adf_stat",
    "hedge_ratio",
    "zscore_current",
    "overbought_signals",
    "oversold_signals",
    "spread_mean",
    "spread_std",
    "price_1_current",
    "price_2_current",
    "total_symbols",
    "total_cointegrated_pairs",
    "analysis_candles",
]


def _output_dir():
    return Path(__file__).resolve().parent / "output"


def _report_path():
    return _output_dir() / "4_summary_report.csv"


def _display_report_path(report_path):
    try:
        return str(report_path.relative_to(Path(__file__).resolve().parent))
    except ValueError:
        return str(report_path)


def _clear_summary_report(reason, logger=None):
    """
    Replace stale summary rows with a header-only report.

    The execution engine uses 2_cointegrated_pairs.csv as its source of truth.
    The summary report is a display artifact, so leaving old rows around after a
    no-pairs scan is more misleading than an empty report.
    """
    output_dir = _output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = _report_path()
    pd.DataFrame(columns=REPORT_COLUMNS).to_csv(report_path, index=False)
    message = f"Summary report cleared: no current pair rows ({reason})."
    print(message)
    if logger:
        logger.warning(message)
    return _display_report_path(report_path)


def _load_inputs():
    base_dir = Path(__file__).resolve().parent
    output_dir = _output_dir()
    price_path = output_dir / "1_price_list.json"
    coint_path = output_dir / "2_cointegrated_pairs.csv"

    if not price_path.exists():
        print(f"ERROR: Required file not found - {price_path}")
        return None, None
    if not coint_path.exists():
        print(f"ERROR: Required file not found - {coint_path}")
        return None, None

    with price_path.open("r", encoding="utf-8") as handle:
        price_data = json.load(handle)
    try:
        df_coint = pd.read_csv(coint_path)
    except Exception:
        print(f"ERROR: Could not read cointegrated pairs CSV - {coint_path}")
        return price_data, pd.DataFrame()

    return price_data, df_coint


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_pair_stats(row, price_data, rank, summary):
    sym_1 = row.get("sym_1")
    sym_2 = row.get("sym_2")
    if not sym_1 or not sym_2:
        return None

    data_1 = price_data.get(sym_1, {})
    data_2 = price_data.get(sym_2, {})
    klines_1 = data_1.get("klines") or []
    klines_2 = data_2.get("klines") or []
    prices_1 = np.array(extract_close_prices(klines_1), dtype=float)
    prices_2 = np.array(extract_close_prices(klines_2), dtype=float)

    if prices_1.size == 0 or prices_2.size == 0:
        return None

    prices_1 = prices_1[np.isfinite(prices_1)]
    prices_2 = prices_2[np.isfinite(prices_2)]
    prices_1 = prices_1[prices_1 > 0]
    prices_2 = prices_2[prices_2 > 0]

    if prices_1.size == 0 or prices_2.size == 0:
        return None

    min_len = min(len(prices_1), len(prices_2))
    if min_len < 2:
        return None
    if len(prices_1) != len(prices_2):
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

    hedge_ratio = _safe_float(row.get("hedge_ratio"))
    if hedge_ratio is None or not np.isfinite(hedge_ratio):
        return None

    log_prices_1 = np.log(prices_1)
    log_prices_2 = np.log(prices_2)
    spread = calculate_spread(log_prices_1, log_prices_2, hedge_ratio)
    zscore = calculate_zscore(spread)

    zscore_clean = zscore[np.isfinite(zscore)]
    zscore_current = float(zscore_clean[-1]) if zscore_clean.size else None
    overbought = int((zscore_clean > 2).sum()) if zscore_clean.size else 0
    oversold = int((zscore_clean < -2).sum()) if zscore_clean.size else 0

    return {
        "generated_at": summary["generated_at"],
        "rank": rank,
        "sym_1": sym_1,
        "sym_2": sym_2,
        "zero_crossings": _safe_float(row.get("zero_crossing")),
        "p_value": _safe_float(row.get("p_value")),
        "adf_stat": _safe_float(row.get("adf_stat")),
        "hedge_ratio": hedge_ratio,
        "zscore_current": zscore_current,
        "overbought_signals": overbought,
        "oversold_signals": oversold,
        "spread_mean": float(np.mean(spread)),
        "spread_std": float(np.std(spread)),
        "price_1_current": float(prices_1[-1]),
        "price_2_current": float(prices_2[-1]),
        "total_symbols": summary["total_symbols"],
        "total_cointegrated_pairs": summary["total_cointegrated_pairs"],
        "analysis_candles": summary["analysis_candles"],
    }


def generate_summary_report(top_n=3):
    """
    Generate CSV summary report.

    Args:
        top_n: Number of top pairs to include (default: 3)
    """
    logger = get_strategy_logger()

    price_data, df_coint = _load_inputs()
    if price_data is None or df_coint is None:
        return _clear_summary_report("missing required input", logger)

    if len(df_coint) == 0:
        print("Summary report skipped: no cointegrated pairs.")
        logger.warning("Summary report skipped: no cointegrated pairs")
        return _clear_summary_report("no cointegrated pairs", logger)

    first_symbol = next(iter(price_data.values()), {})
    symbol_info = first_symbol.get("symbol_info", {}) if isinstance(first_symbol, dict) else {}
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_symbols": len(price_data),
        "total_cointegrated_pairs": len(df_coint),
        "analysis_candles": int(symbol_info.get("total_klines", 0) or 0),
    }

    top_pairs = df_coint.head(top_n)
    rows = []
    for idx, row in top_pairs.reset_index(drop=True).iterrows():
        stats = _compute_pair_stats(row, price_data, idx + 1, summary)
        if stats:
            rows.append(stats)

    if not rows:
        print("Summary report skipped: no valid pair stats.")
        logger.warning("Summary report skipped: no valid pair stats")
        return _clear_summary_report("no valid pair stats", logger)

    report_path = _report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    df_report = pd.DataFrame(rows)
    df_report = df_report.reindex(columns=REPORT_COLUMNS)
    df_report.to_csv(report_path, index=False)

    rel_path = _display_report_path(report_path)

    print(f"Summary report saved: {rel_path} (rows {len(df_report)})")
    logger.info("Summary report saved: %s rows=%d", rel_path, len(df_report))

    return str(rel_path)


if __name__ == "__main__":
    generate_summary_report(top_n=3)
