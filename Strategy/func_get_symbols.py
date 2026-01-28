"""
    Get tradeable symbols filtered by maker fees for OKX
    Based on OKX API v5 documentation
"""

from config_strategy_api import public_session, account_session, time_frame
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
import threading


class RateLimiter:
    """
    Token bucket rate limiter to respect OKX API limits.
    OKX limit: 20 requests per 2 seconds for most endpoints
    """
    def __init__(self, max_requests_per_second=10):
        self.max_requests = max_requests_per_second
        self.tokens = max_requests_per_second
        self.lock = threading.Lock()
        self.last_update = time.time()

    def acquire(self):
        """Wait until a token is available, then consume it"""
        with self.lock:
            now = time.time()
            # Refill tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.max_requests, self.tokens + elapsed * self.max_requests)
            self.last_update = now

            # If no tokens available, sleep until we can get one
            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.max_requests
                time.sleep(sleep_time)
                self.tokens = 1

            # Consume one token
            self.tokens -= 1


# Global rate limiter instance
# OKX limit: 20 req/2sec, but we use 5 req/sec for safety margin
rate_limiter = RateLimiter(max_requests_per_second=5)

def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_fee_rates_for_type(inst_type):
    """Get fee rates for an instrument type (OKX has same fees per type, not per instrument)"""
    try:
        # Get fee rates by instrument type only
        fee_response = account_session.get_fee_rates(
            instType=inst_type
        )

        print(f"\nDEBUG: Fetching fee rates for {inst_type}")
        print(f"  Response code: {fee_response.get('code')}")
        print(f"  Response msg: {fee_response.get('msg')}")
        print(f"  Response data: {fee_response.get('data')}")

        # OKX returns: {'code': '0', 'msg': '', 'data': [...]}
        if fee_response['code'] == '0' and fee_response['data']:
            # OKX returns fee rates by category/level
            return fee_response['data']
        else:
            print(f"ERROR: Failed to get fee rates for {inst_type}")
            print(f"  Code: {fee_response.get('code')}, Msg: {fee_response.get('msg')}")
            return None

    except Exception as e:
        print(f"EXCEPTION getting fee rates: {e}")
        return None


def get_symbols_by_maker_fees(
        inst_type="SWAP",  # SPOT, SWAP, FUTURES, OPTION
        max_maker_fee=0.0002,  # 0.02%
        max_workers=3,  # Parallel threads (safe default)
):
    """
    Get instruments filtered by maker fees (OPTIMIZED with parallel requests)
    Returns both low-fee and negative-fee (rebate) instruments

    Args:
        inst_type: Instrument type (SPOT, SWAP, FUTURES, OPTION)
        max_maker_fee: Maximum maker fee threshold for low-fee filtering
        max_workers: Number of parallel threads (default: 3)

    Returns:
        dict: {
            'low_fee_symbols': List of symbols with maker fee < max_maker_fee,
            'negative_fee_symbols': List of symbols with negative maker fees (rebates)
        }
    """

    # Step 1: Get all instruments
    print("Fetching all instruments...")
    start_time = time.time()

    instruments_response = public_session.get_instruments(
        instType=inst_type
    )

    # OKX response format: {'code': '0', 'msg': '', 'data': [...]}
    if instruments_response['code'] != '0':
        print(f"Error: {instruments_response['msg']}")
        return {'low_fee_symbols': [], 'negative_fee_symbols': []}

    all_instruments = instruments_response['data']

    # Filter only live/active instruments
    active_instruments = [inst for inst in all_instruments if inst.get('state') == 'live']

    print(f"Found {len(all_instruments)} total instruments")
    print(f"Found {len(active_instruments)} active/live instruments\n")

    # Step 2: Get fee rates for this instrument type (same for all instruments of same type)
    print(f"Fetching fee rates for {inst_type}...")
    fee_data = _get_fee_rates_for_type(inst_type)

    if not fee_data:
        print("ERROR: Could not fetch fee rates")
        return {'low_fee_symbols': [], 'negative_fee_symbols': [], 'all_fees': []}

    # Extract fee rates (usually first entry is the user's fee tier)
    fee_info = fee_data[0]
    maker_fee = float(fee_info.get('maker', 0))
    taker_fee = float(fee_info.get('taker', 0))

    print(f"\n{'=' * 60}")
    print(f"YOUR FEE RATES for {inst_type}:")
    print(f"  Maker: {maker_fee * 100:.4f}%")
    print(f"  Taker: {taker_fee * 100:.4f}%")
    print(f"  Category: {fee_info.get('category', 'N/A')}")
    print(f"{'=' * 60}\n")

    # Step 3: Apply the same fee to all instruments
    low_fee_symbols = []
    negative_fee_symbols = []
    all_fees = []

    for instrument in active_instruments:
        inst_id = instrument['instId']
        result = {
            'symbol': inst_id,
            'base_coin': instrument.get('baseCcy', ''),
            'quote_coin': instrument.get('quoteCcy', ''),
            'settle_coin': instrument.get('settleCcy', ''),
            'period': time_frame,
            'maker_fee': maker_fee,
            'taker_fee': taker_fee,
            'status': instrument.get('state', 'unknown'),
            'category': fee_info.get('category', ''),
            'inst_type': inst_type,
            'min_sz': _safe_float(instrument.get('minSz')),
            'lot_sz': _safe_float(instrument.get('lotSz'))
        }

        # Track all fees
        all_fees.append((inst_id, maker_fee, taker_fee))

        # Filter: negative maker fee (rebate)
        if maker_fee < 0:
            result['maker_fee_pct'] = f"{maker_fee * 100:.4f}%"
            result['taker_fee_pct'] = f"{taker_fee * 100:.4f}%"
            result['maker_rebate'] = f"{abs(maker_fee) * 100:.4f}%"
            negative_fee_symbols.append(result)

        # Filter: maker fee < threshold (but not negative)
        elif maker_fee <= max_maker_fee:
            result['maker_fee_pct'] = f"{maker_fee * 100:.4f}%"
            result['taker_fee_pct'] = f"{taker_fee * 100:.4f}%"
            low_fee_symbols.append(result)

    elapsed = time.time() - start_time

    # Find lowest maker fees
    if all_fees:
        all_fees_sorted = sorted(all_fees, key=lambda x: x[1])  # Sort by maker fee
        lowest_10 = all_fees_sorted[:10]

        print(f"\n{'=' * 60}")
        print(f"LOWEST 10 MAKER FEES:")
        print(f"{'=' * 60}")
        for symbol, maker, taker in lowest_10:
            print(f"{symbol:<20} Maker: {maker * 100:.4f}% | Taker: {taker * 100:.4f}%")

    print(f"\n{'=' * 60}")
    print(f"✅ Completed in {elapsed:.2f} seconds")
    print(f"📊 Found {len(low_fee_symbols)} symbols with maker fee < {max_maker_fee * 100}%")
    print(f"💰 Found {len(negative_fee_symbols)} symbols with maker rebates")
    print(f"{'=' * 60}\n")

    return {
        'low_fee_symbols': low_fee_symbols,
        'negative_fee_symbols': negative_fee_symbols,
        'all_fees': all_fees
    }


if __name__ == "__main__":
    """Test the function"""
    result = get_symbols_by_maker_fees(
        inst_type="SWAP",  # Perpetual swaps
        max_maker_fee=0.0002,  # Less than 0.02%
        max_workers=3
    )

    print("\n" + "="*60)
    print("LOW FEE SYMBOLS (Maker < 0.02%):")
    print("="*60)
    for symbol in result['low_fee_symbols'][:10]:  # Show first 10
        print(f"{symbol['symbol']:<20} Maker: {symbol['maker_fee_pct']:<10} Taker: {symbol['taker_fee_pct']}")

    print("\n" + "="*60)
    print("NEGATIVE FEE SYMBOLS (Maker Rebates):")
    print("="*60)
    for symbol in result['negative_fee_symbols'][:10]:  # Show first 10
        print(f"{symbol['symbol']:<20} Rebate: {symbol['maker_rebate']:<10} Taker: {symbol['taker_fee_pct']}")
