"""
Pre-live checklist: fetch fee tier and scan recent bills for rebates/credits.

Usage (from Execution/):
  python pre_live_checklist.py --mode live --inst-type SWAP
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from okx.Account import AccountAPI


def _load_env():
    if not load_dotenv:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _clean_env(value: str) -> str:
    value = (value or "").strip()
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1].strip()
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-live fee tier + rebate/credit checklist for OKX."
    )
    parser.add_argument(
        "--mode",
        choices=["live", "demo"],
        help="Override OKX_FLAG (live=0, demo=1).",
    )
    parser.add_argument(
        "--flag",
        choices=["0", "1"],
        help="Override OKX_FLAG directly (0=live, 1=demo).",
    )
    parser.add_argument(
        "--inst-type",
        default=os.getenv("STATBOT_FEE_INST_TYPE", "SWAP"),
        help="Instrument type for fee rates and bills (default: SWAP).",
    )
    parser.add_argument(
        "--inst-id",
        default=os.getenv("STATBOT_FEE_INST_ID", ""),
        help="Optional instId to scope fee rates.",
    )
    parser.add_argument(
        "--bill-limit",
        type=int,
        default=int(os.getenv("STATBOT_BILL_LIMIT", "50")),
        help="Number of recent bills to fetch (default: 50).",
    )
    parser.add_argument(
        "--show-bills",
        action="store_true",
        help="Print all bills returned (use with small --bill-limit).",
    )
    return parser.parse_args()


def _resolve_flag(args: argparse.Namespace) -> str:
    if args.flag in ("0", "1"):
        return args.flag
    if args.mode == "live":
        return "0"
    if args.mode == "demo":
        return "1"
    env_flag = os.getenv("OKX_FLAG", "").strip()
    if env_flag in ("0", "1"):
        return env_flag
    return "1"


def _require_env(name: str) -> str:
    value = _clean_env(os.getenv(name, ""))
    if not value:
        raise RuntimeError(f"Missing {name} in environment/.env")
    return value


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_ts(value: str) -> str:
    if not value:
        return ""
    try:
        ts = int(float(value))
        if ts > 10**12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return str(value)


def _print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _print_fee_rates(account_session: AccountAPI, inst_type: str, inst_id: str) -> None:
    _print_header("FEE TIER CHECK")
    response = account_session.get_fee_rates(instType=inst_type, instId=inst_id)
    if response.get("code") != "0":
        print(f"ERROR: get_fee_rates failed: {response.get('msg')}")
        return

    data = response.get("data", [])
    print(f"Returned fee entries: {len(data)}")
    if not data:
        return

    max_show = 10
    for row in data[:max_show]:
        level = row.get("level", "")
        maker = row.get("maker", "")
        taker = row.get("taker", "")
        inst_type_row = row.get("instType", inst_type)
        inst_id_row = row.get("instId", "")
        label = f"{inst_type_row}"
        if inst_id_row:
            label += f" {inst_id_row}"
        print(f"- {label} | level={level} maker={maker} taker={taker}")

    if len(data) > max_show:
        print(f"... showing {max_show} of {len(data)} entries")


def _rebate_like(bill: dict) -> bool:
    keys = ["type", "subType", "memo", "note", "remark"]
    for key in keys:
        val = str(bill.get(key, "")).lower()
        if any(word in val for word in ("rebate", "referral", "reward", "commission", "maker")):
            return True
    return False


def _print_bills(account_session: AccountAPI, inst_type: str, limit: int, show_all: bool) -> None:
    _print_header("RECENT BILLS (REBATABLE CREDITS)")
    response = account_session.get_account_bills(instType=inst_type, limit=str(limit))
    if response.get("code") != "0":
        print(f"ERROR: get_account_bills failed: {response.get('msg')}")
        return

    bills = response.get("data", [])
    print(f"Returned bills: {len(bills)} (limit={limit})")
    if not bills:
        return

    rows = []
    for bill in bills:
        bal_chg = _safe_float(bill.get("balChg"), 0.0)
        rows.append(
            {
                "ts": _format_ts(bill.get("ts")),
                "ccy": bill.get("ccy", ""),
                "bal_chg": bal_chg,
                "type": bill.get("type", ""),
                "sub_type": bill.get("subType", ""),
                "inst_id": bill.get("instId", ""),
                "rebate_like": _rebate_like(bill),
            }
        )

    total_pos_usdt = sum(r["bal_chg"] for r in rows if r["ccy"] == "USDT" and r["bal_chg"] > 0)
    total_neg_usdt = sum(r["bal_chg"] for r in rows if r["ccy"] == "USDT" and r["bal_chg"] < 0)
    print(f"USDT credits: {total_pos_usdt:.6f} | USDT debits: {total_neg_usdt:.6f}")

    rebate_hits = [r for r in rows if r["rebate_like"]]
    if rebate_hits:
        print(f"Rebate-like entries detected: {len(rebate_hits)}")
    else:
        print("Rebate-like entries detected: 0 (not definitive)")

    if show_all:
        print("\nAll bills:")
        for r in rows:
            print(
                f"- {r['ts']} {r['ccy']} balChg={r['bal_chg']:.6f} "
                f"type={r['type']} subType={r['sub_type']} instId={r['inst_id']}"
            )
        return

    positives = [r for r in rows if r["bal_chg"] > 0]
    positives = sorted(positives, key=lambda x: abs(x["bal_chg"]), reverse=True)[:10]
    if positives:
        print("\nTop credit entries:")
        for r in positives:
            print(
                f"- {r['ts']} {r['ccy']} +{r['bal_chg']:.6f} "
                f"type={r['type']} subType={r['sub_type']} instId={r['inst_id']}"
            )

    negatives = [r for r in rows if r["bal_chg"] < 0]
    negatives = sorted(negatives, key=lambda x: abs(x["bal_chg"]), reverse=True)[:10]
    if negatives:
        print("\nTop debit entries:")
        for r in negatives:
            print(
                f"- {r['ts']} {r['ccy']} {r['bal_chg']:.6f} "
                f"type={r['type']} subType={r['sub_type']} instId={r['inst_id']}"
            )


def main() -> None:
    _load_env()
    args = _parse_args()
    flag = _resolve_flag(args)
    mode_label = "live" if flag == "0" else "demo"

    api_key = _require_env("OKX_API_KEY")
    api_secret = _require_env("OKX_API_SECRET")
    passphrase = _require_env("OKX_PASSPHRASE")

    account_session = AccountAPI(
        api_key=api_key,
        api_secret_key=api_secret,
        passphrase=passphrase,
        flag=flag,
        debug=False,
    )
    account_session.timeout = 10.0

    _print_header("PRE-LIVE CHECKLIST")
    print(f"Mode: {mode_label} (OKX_FLAG={flag})")
    print(f"InstType: {args.inst_type}")
    if args.inst_id:
        print(f"InstId: {args.inst_id}")
    print(f"Bill limit: {args.bill_limit}")

    _print_fee_rates(account_session, args.inst_type, args.inst_id)
    _print_bills(account_session, args.inst_type, args.bill_limit, args.show_bills)

    _print_header("NEXT STEPS")
    print("- Confirm your fee level and maker/taker rates above.")
    print("- If you expect rebates, look for positive USDT credits and rebate-like entries.")
    print("- For a definitive view, compare bills with the OKX fee schedule for your region.")


if __name__ == "__main__":
    main()
