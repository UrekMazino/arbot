# OKX Statistical Arbitrage Bot

Trading bot for OKX exchange implementing statistical arbitrage strategies.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure API credentials:
   - Copy `Strategy/.env` and update with your OKX API credentials
   - Get API keys from: https://www.okx.com/account/my-api

3. API Permissions Required:
   - Read (for market data and account info)
   - Trade (for placing/canceling orders)

## Configuration

Edit `Strategy/.env`:
```env
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_PASSPHRASE=your_passphrase_here
OKX_FLAG=1  # 1 = demo trading, 0 = live trading
```

## Usage

Run the strategy:
```bash
cd Strategy
python main_strategy.py
```

Test getting symbols by maker fees:
```bash
cd Strategy
python func_get_symbols.py
```

## Documentation

For a detailed explanation of the bot's architecture, trading logic, risk management, and computations, please see:
- **[BOT_DOCUMENTATION.md](BOT_DOCUMENTATION.md)**: Comprehensive guide to the Execution system.
- **[KILL_SWITCH_STATE_MACHINE.md](KILL_SWITCH_STATE_MACHINE.md)**: Detailed state machine transitions.

## Features

### Step 1: Get Tradeable Symbols by Maker Fees
- Fetches all available instruments (SWAP/Perpetual contracts)
- Retrieves trading fees for each instrument
- Filters symbols by maker fee threshold
- Identifies symbols with negative maker fees (rebates)
- Uses parallel processing with rate limiting

## API Documentation

- OKX API v5: https://www.okx.com/docs-v5/en/
- Public Data: https://www.okx.com/docs-v5/en/#public-data-rest-api
- Trading Account: https://www.okx.com/docs-v5/en/#trading-account-rest-api
- Order Book Trading: https://www.okx.com/docs-v5/en/#order-book-trading-trade

## Instrument Types

- `SWAP`: Perpetual swaps (no expiry)
- `FUTURES`: Futures contracts (with expiry)
- `SPOT`: Spot trading pairs
- `OPTION`: Options contracts

## Safety Features

- Rate limiting (5 req/sec default)
- Demo trading mode (OKX_FLAG=1)
- Error handling and retries
- Progress tracking
