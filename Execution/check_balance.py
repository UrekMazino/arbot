"""
Diagnostic script to check OKX account balances and configuration.
Run this to see where your USDT is located and how much is available for trading.
"""

from config_execution_api import account_session, td_mode, pos_mode, ticker_1, ticker_2, tradeable_capital_usdt
from func_execution_calls import get_min_capital_requirements
from okx.Funding import FundingAPI
from okx import consts as okx_consts
import os

# Initialize funding session
api_key = os.getenv("OKX_API_KEY")
secret_key = os.getenv("OKX_SECRET_KEY")
passphrase = os.getenv("OKX_PASSPHRASE")
flag = "1"  # 1 for demo trading

funding_session = FundingAPI(api_key, secret_key, passphrase, False, flag)
import json

def check_all_balances():
    """Check balances across all OKX account types."""

    print("\n" + "="*60)
    print("OKX ACCOUNT DIAGNOSTICS")
    print("="*60)

    min_pair_equity = None
    required_equity = tradeable_capital_usdt
    try:
        req_1 = get_min_capital_requirements(ticker_1)
        req_2 = get_min_capital_requirements(ticker_2)
        min_1 = float(req_1.get("min_capital") or 0)
        min_2 = float(req_2.get("min_capital") or 0)
        if req_1.get("ok") and req_2.get("ok") and min_1 > 0 and min_2 > 0:
            min_pair_equity = max(min_1, min_2) * 2
    except Exception:
        min_pair_equity = None

    if min_pair_equity and min_pair_equity > required_equity:
        required_equity = min_pair_equity

    # 1. Trading Account Balance
    print("\n[1] TRADING ACCOUNT (for opening positions)")
    print("-" * 60)
    try:
        balance_res = account_session.get_account_balance()
        if balance_res.get("code") == "0":
            data = balance_res.get("data", [])
            if data:
                details = data[0].get("details", [])
                for det in details:
                    ccy = det.get("ccy")
                    if ccy == "USDT":
                        total_eq = float(det.get("eq", 0))
                        avail_bal = float(det.get("availBal", 0))
                        frozen = float(det.get("frozenBal", 0))
                        cash_bal = float(det.get("cashBal", 0))

                        print(f"Currency: {ccy}")
                        print(f"  Total Equity: {total_eq:.2f} USDT")
                        print(f"  Available: {avail_bal:.2f} USDT (can trade with this)")
                        print(f"  Frozen: {frozen:.2f} USDT (in open orders)")
                        print(f"  Cash Balance: {cash_bal:.2f} USDT")

                        if min_pair_equity:
                            print(f"  Recommended min equity for {ticker_1}/{ticker_2}: {min_pair_equity:.2f} USDT")

                        if avail_bal < required_equity:
                            print(f"  WARNING: Available balance ({avail_bal:.2f}) < {required_equity:.2f} USDT")
                            print(f"     Configured tradeable capital: {tradeable_capital_usdt:.2f} USDT")
        else:
            print(f"❌ Error: {balance_res.get('msg')}")
    except Exception as e:
        print(f"❌ Failed to fetch trading account: {e}")

    # 2. Funding Account Balance
    print("\n[2] FUNDING ACCOUNT (cold storage)")
    print("-" * 60)
    try:
        funding_res = funding_session.get_balances(ccy="USDT")
        if funding_res.get("code") == "0":
            data = funding_res.get("data", [])
            for item in data:
                ccy = item.get("ccy")
                if ccy == "USDT":
                    avail = float(item.get("availBal", 0))
                    bal = float(item.get("bal", 0))
                    frozen = float(item.get("frozenBal", 0))

                    print(f"Currency: {ccy}")
                    print(f"  Total Balance: {bal:.2f} USDT")
                    print(f"  Available: {avail:.2f} USDT")
                    print(f"  Frozen: {frozen:.2f} USDT")

                    if avail > 100:
                        print(f"  TIP: You have {avail:.2f} USDT here that can't be used for trading")
                        print(f"     Transfer it to Trading Account to use it")
        else:
            print(f"Error: {funding_res.get('msg')}")
    except Exception as e:
        print(f"Failed to fetch funding account: {e}")

    # 3. Current Configuration
    print("\n[3] BOT CONFIGURATION")
    print("-" * 60)
    print(f"Trade Mode: {td_mode}")
    print(f"Position Mode: {pos_mode}")

    if td_mode == "isolated":
        print("\nISOLATED MODE REQUIREMENTS:")
        print("  - Each position needs separate margin/collateral")
        if min_pair_equity:
            print(f"  - Recommended equity for {ticker_1}/{ticker_2}: {min_pair_equity:.2f} USDT")
        print(f"  - Configured tradeable capital: {tradeable_capital_usdt:.2f} USDT")
        print(f"  - Suggested available balance: {required_equity:.2f} USDT")
    else:
        print("\nCROSS MODE:")
        print("  - All positions share account margin")
        print("  - More capital efficient but higher risk")

    # 4. Recommendations
    print("\n[4] RECOMMENDATIONS")
    print("-" * 60)
    print("If orders are failing with 'insufficient balance':")
    print("  1. Check Trading Account available balance above")
    print("  2. If funds are in Funding Account, transfer to Trading")
    print("  3. Or switch to 'cross' mode (more capital efficient)")
    print("  4. Or reduce tradeable_capital_usdt in config")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    check_all_balances()
