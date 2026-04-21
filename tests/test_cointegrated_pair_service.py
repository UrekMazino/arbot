from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Platform.api.app.services import cointegrated_pairs as cp


def _write_price_json(path: Path) -> None:
    rows_a = []
    rows_b = []
    for idx, (a, b) in enumerate([(10.0, 20.0), (10.2, 20.1), (10.1, 20.2), (10.4, 20.0)]):
        ts = str(1_776_700_000_000 + idx * 60_000)
        rows_a.append({"timestamp": ts, "close": a})
        rows_b.append({"timestamp": ts, "close": b})
    path.write_text(
        json.dumps(
            {
                "AAA-USDT-SWAP": {"klines": rows_a},
                "BBB-USDT-SWAP": {"klines": rows_b},
            }
        ),
        encoding="utf-8",
    )


def test_cointegrated_pair_catalog_and_detail(monkeypatch, tmp_path):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    price_json = tmp_path / "1_price_list.json"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "p_value": 0.001,
                "adf_stat": -4.5,
                "hedge_ratio": 0.8,
                "zero_crossing": 7,
                "pair_liquidity_min": 1234.5,
                "pair_order_capacity_usdt": 6789.0,
            }
        ]
    ).to_csv(coint_csv, index=False)
    _write_price_json(price_json)
    status_json.write_text(
        json.dumps({"latest_attempt_rows": 0, "canonical_rows": 1, "preserved_existing": True}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "PRICE_JSON", price_json)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)

    catalog = cp.list_cointegrated_pairs()
    detail = cp.get_cointegrated_pair_detail("AAA-USDT-SWAP", "BBB-USDT-SWAP", limit=50)

    assert catalog["pair_count"] == 1
    assert catalog["status"]["preserved_existing"] is True
    assert catalog["pairs"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert detail["pair"]["zero_crossing"] == 7
    assert len(detail["points"]) == 4
    assert detail["stats"]["zscore_current"] is not None
