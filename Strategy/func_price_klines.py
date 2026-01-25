"""
    Get historical klines/candlesticks for OKX instruments
    OKX API: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks

    Bar intervals: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    Limit: max 100 candles per request (default 100)
"""

from config_strategy_api import market_session, time_frame, kline_limit


def get_price_klines(inst_id):
    """
    Get historical candlestick data for an instrument

    Args:
        inst_id: Instrument ID (e.g., 'BTC-USDT-SWAP')

    Returns:
        dict: {'code': '0', 'msg': '', 'data': [[timestamp, open, high, low, close, vol, volCcy], ...]}
    """
    try:
        # Get candlesticks from OKX
        # OKX limit is 100 candles per request by default
        prices = market_session.get_candlesticks(
            instId=inst_id,
            bar=time_frame,  # '1m', '5m', '1H', etc.
            limit=str(kline_limit)  # OKX expects string
        )

        # OKX response format: {'code': '0', 'msg': '', 'data': [[...], ...]}
        # Each data item: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]

        # Return only if we have the expected number of klines
        if prices['code'] == '0' and prices['data'] and len(prices['data']) >= kline_limit:
            return prices
        elif prices['code'] == '0' and prices['data']:
            # Return partial data if we got some but not enough
            print(f"  Warning: Got {len(prices['data'])} candles, expected {kline_limit}")
            return prices
        else:
            # Return error or empty result
            print(f"  Error getting klines: {prices.get('msg', 'Unknown error')}")
            return {'code': '1', 'msg': 'Insufficient data', 'data': []}

    except Exception as e:
        print(f"  Exception getting klines: {e}")
        return {'code': '1', 'msg': str(e), 'data': []}
