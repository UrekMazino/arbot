"""
OKX REST API Methods Reference Generator
Generates an HTML documentation page for OKX API endpoints
Based on OKX API v5 documentation: https://www.okx.com/docs-v5/en/
"""
import webbrowser
import os

# Public REST endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    'get_instruments',
    'get_delivery_exercise_history',
    'get_open_interest',
    'get_funding_rate',
    'get_funding_rate_history',
    'get_price_limit',
    'get_option_market_data',
    'get_estimated_delivery_exercise_price',
    'get_discount_rate_interest_free_quota',
    'get_system_time',
    'get_mark_price',
    'get_position_tiers',
    'get_interest_rate_loan_quota',
    'get_vip_interest_rate_loan_quota',
    'get_underlying',
    'get_insurance_fund',
    'get_unit_convert',
    'get_tickers',
    'get_index_tickers',
    'get_order_book',
    'get_candlesticks',
    'get_candlesticks_history',
    'get_index_candlesticks',
    'get_mark_price_candlesticks',
    'get_trades',
    'get_volume',
    'get_oracle',
    'get_exchange_rate',
    'get_index_components',
    'get_block_tickers',
    'get_block_trades',
}

# Public WebSocket channels that don't require authentication
PUBLIC_WS_CHANNELS = {
    'ws_tickers',
    'ws_candlesticks',
    'ws_trades',
    'ws_order_book',
    'ws_option_trades',
    'ws_call_auction',
    'ws_instruments',
    'ws_open_interest',
    'ws_funding_rate',
    'ws_price_limit',
    'ws_option_summary',
    'ws_mark_price',
    'ws_index_tickers',
    'ws_liquidation_orders',
    'ws_adl_warning',
    'ws_economic_calendar',
}

# Private WebSocket channels that require authentication
PRIVATE_WS_CHANNELS = {
    'ws_orders',
    'ws_fills',
    'ws_account',
    'ws_positions',
    'ws_balance_positions',
    'ws_position_risk',
    'ws_account_greeks',
    'ws_deposit_info',
    'ws_withdrawal_info',
}

# Mapping of OKX methods to documentation URLs
DOC_URL_MAP = {
    # Market Data - Public
    'get_tickers': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-tickers',
    'get_index_tickers': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-index-tickers',
    'get_order_book': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-order-book',
    'get_candlesticks': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks',
    'get_candlesticks_history': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks-history',
    'get_index_candlesticks': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-index-candlesticks',
    'get_mark_price_candlesticks': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-mark-price-candlesticks',
    'get_trades': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-trades',
    'get_volume': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-24h-total-volume',
    'get_oracle': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-oracle',
    'get_exchange_rate': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-exchange-rate',
    'get_index_components': 'https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-index-components',
    'get_block_tickers': 'https://www.okx.com/docs-v5/en/#block-trading-market-data-get-block-tickers',
    'get_block_trades': 'https://www.okx.com/docs-v5/en/#block-trading-market-data-get-block-trades',

    # Public Data
    'get_instruments': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments',
    'get_delivery_exercise_history': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-delivery-exercise-history',
    'get_open_interest': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-open-interest',
    'get_funding_rate': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate',
    'get_funding_rate_history': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-funding-rate-history',
    'get_price_limit': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-limit-price',
    'get_option_market_data': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-option-market-data',
    'get_estimated_delivery_exercise_price': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-estimated-delivery-exercise-price',
    'get_discount_rate_interest_free_quota': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-discount-rate-and-interest-free-quota',
    'get_system_time': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-system-time',
    'get_mark_price': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-mark-price',
    'get_position_tiers': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-position-tiers',
    'get_interest_rate_loan_quota': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-interest-rate-and-loan-quota',
    'get_vip_interest_rate_loan_quota': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-vip-interest-rate-and-loan-quota',
    'get_underlying': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-underlying',
    'get_insurance_fund': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-get-insurance-fund',
    'get_unit_convert': 'https://www.okx.com/docs-v5/en/#public-data-rest-api-unit-convert',

    # Trading - Order
    'place_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-order',
    'place_multiple_orders': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-place-multiple-orders',
    'cancel_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-cancel-order',
    'cancel_multiple_orders': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-cancel-multiple-orders',
    'amend_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-amend-order',
    'amend_multiple_orders': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-amend-multiple-orders',
    'close_positions': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-post-close-positions',
    'get_order_details': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-details',
    'get_order_list': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-list',
    'get_order_history': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-history-last-7-days',
    'get_order_history_archive': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-history-last-3-months',
    'get_transaction_details': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-transaction-details-last-3-days',
    'get_transaction_history': 'https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-transaction-details-last-3-months',

    # Trading - Algo Orders
    'place_algo_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-post-place-algo-order',
    'cancel_algo_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-post-cancel-algo-order',
    'cancel_advance_algo_order': 'https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-post-cancel-advance-algo-order',
    'get_algo_order_list': 'https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-get-algo-order-list',
    'get_algo_order_history': 'https://www.okx.com/docs-v5/en/#order-book-trading-algo-trading-get-algo-order-history',

    # Account
    'get_account_balance': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-balance',
    'get_positions': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-positions',
    'get_positions_history': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-positions-history',
    'get_account_position_risk': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-account-and-position-risk',
    'get_bills_details': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-bills-details-last-7-days',
    'get_bills_archive': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-bills-details-last-3-months',
    'get_account_config': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-account-configuration',
    'set_position_mode': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-set-position-mode',
    'set_leverage': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-set-leverage',
    'get_max_size': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-maximum-buy-sell-amount-or-open-amount',
    'get_max_available_size': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-maximum-available-tradable-amount',
    'increase_decrease_margin': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-increase-decrease-margin',
    'get_leverage': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-leverage',
    'get_max_loan': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-the-maximum-loan-of-instrument',
    'get_fee_rates': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-fee-rates',
    'get_interest_accrued': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-interest-accrued-data',
    'get_interest_rate': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-interest-rate',
    'set_greeks': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-set-greeks-pa-bs',
    'set_isolated_mode': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-set-isolated-mode',
    'get_max_withdrawals': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-maximum-withdrawals',
    'get_account_risk_state': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-account-risk-state',
    'vip_loans_borrow_repay': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-post-manual-borrow-and-repay',
    'get_borrow_repay_history': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-borrow-and-repay-history',
    'get_vip_interest_accrued': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-vip-interest-accrued-data',
    'get_vip_interest_deducted': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-vip-interest-deducted-data',
    'get_vip_loan_order_list': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-vip-loan-order-list',
    'get_vip_loan_order_detail': 'https://www.okx.com/docs-v5/en/#trading-account-rest-api-get-vip-loan-order-detail',

    # Funding
    'get_currencies': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-currencies',
    'get_balance': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-balance',
    'get_account_asset_valuation': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-account-asset-valuation',
    'funds_transfer': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-funds-transfer',
    'get_funds_transfer_state': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-funds-transfer-state',
    'asset_bills_details': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-asset-bills-details',
    'lightning_deposits': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-lightning-deposits',
    'get_deposit_address': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-deposit-address',
    'get_deposit_history': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-deposit-history',
    'withdrawal': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-withdrawal',
    'lightning_withdrawals': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-lightning-withdrawals',
    'cancel_withdrawal': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-cancel-withdrawal',
    'get_withdrawal_history': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-withdrawal-history',
    'small_assets_convert': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-small-assets-convert',
    'get_saving_balance': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-saving-balance',
    'savings_purchase_redemption': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-savings-purchase-redemption',
    'set_lending_rate': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-post-set-lending-rate',
    'get_lending_history': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-lending-history',
    'get_lending_rate_history': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-public-borrow-history-public',
    'get_lending_rate_summary': 'https://www.okx.com/docs-v5/en/#funding-account-rest-api-get-public-borrow-info-public',

    # Sub-Account
    'get_subaccount_list': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-get-sub-account-list',
    'reset_subaccount_apikey': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-post-reset-the-api-key-of-a-sub-account',
    'get_subaccount_trading_balance': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-get-sub-account-trading-balance',
    'get_subaccount_funding_balance': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-get-sub-account-funding-balance',
    'subaccount_transfer': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-post-master-accounts-manage-the-transfers-between-sub-accounts',
    'set_permission_transfer_out': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-post-set-permission-of-transfer-out',
    'get_custody_trading_subaccount_list': 'https://www.okx.com/docs-v5/en/#sub-account-rest-api-get-custody-trading-sub-account-list',

    # Grid Trading
    'place_grid_algo_order': 'https://www.okx.com/docs-v5/en/#grid-trading-post-place-grid-algo-order',
    'amend_grid_algo_order': 'https://www.okx.com/docs-v5/en/#grid-trading-post-amend-grid-algo-order',
    'stop_grid_algo_order': 'https://www.okx.com/docs-v5/en/#grid-trading-post-stop-grid-algo-order',
    'get_grid_algo_order_list': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-algo-order-list',
    'get_grid_algo_order_history': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-algo-order-history',
    'get_grid_algo_order_details': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-algo-order-details',
    'get_grid_algo_sub_orders': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-algo-sub-orders',
    'get_grid_algo_order_positions': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-algo-order-positions',
    'spot_moon_grid_withdraw_income': 'https://www.okx.com/docs-v5/en/#grid-trading-post-spot-moon-grid-withdraw-income',
    'compute_grid_margin_balance': 'https://www.okx.com/docs-v5/en/#grid-trading-post-compute-margin-balance',
    'adjust_grid_margin_balance': 'https://www.okx.com/docs-v5/en/#grid-trading-post-adjust-margin-balance',
    'get_grid_ai_parameter': 'https://www.okx.com/docs-v5/en/#grid-trading-get-grid-ai-parameter-public',

    # WebSocket - Public Channels
    'ws_tickers': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-tickers-channel',
    'ws_candlesticks': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-candlesticks-channel',
    'ws_trades': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-trades-channel',
    'ws_order_book': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-order-book-channel',
    'ws_option_trades': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-option-trades-channel',
    'ws_call_auction': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-call-auction-channel',
    'ws_instruments': 'https://www.okx.com/docs-v5/en/#public-channel-instruments-channel',
    'ws_open_interest': 'https://www.okx.com/docs-v5/en/#public-channel-open-interest-channel',
    'ws_funding_rate': 'https://www.okx.com/docs-v5/en/#public-channel-funding-rate-channel',
    'ws_price_limit': 'https://www.okx.com/docs-v5/en/#public-channel-price-limit-channel',
    'ws_option_summary': 'https://www.okx.com/docs-v5/en/#public-channel-option-summary-channel',
    'ws_mark_price': 'https://www.okx.com/docs-v5/en/#public-channel-mark-price-channel',
    'ws_index_tickers': 'https://www.okx.com/docs-v5/en/#public-channel-index-tickers-channel',
    'ws_liquidation_orders': 'https://www.okx.com/docs-v5/en/#public-channel-liquidation-orders-channel',
    'ws_adl_warning': 'https://www.okx.com/docs-v5/en/#public-channel-adl-warning-channel',
    'ws_economic_calendar': 'https://www.okx.com/docs-v5/en/#public-channel-economic-calendar-channel',

    # WebSocket - Private Channels
    'ws_orders': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-order-channel',
    'ws_fills': 'https://www.okx.com/docs-v5/en/#order-book-trading-ws-fills-channel',
    'ws_account': 'https://www.okx.com/docs-v5/en/#trading-account-ws-account-channel',
    'ws_positions': 'https://www.okx.com/docs-v5/en/#trading-account-ws-positions-channel',
    'ws_balance_positions': 'https://www.okx.com/docs-v5/en/#trading-account-ws-balance-and-position-channel',
    'ws_position_risk': 'https://www.okx.com/docs-v5/en/#trading-account-ws-position-risk-warning',
    'ws_account_greeks': 'https://www.okx.com/docs-v5/en/#trading-account-ws-account-greeks-channel',
    'ws_deposit_info': 'https://www.okx.com/docs-v5/en/#funding-account-ws-deposit-info',
    'ws_withdrawal_info': 'https://www.okx.com/docs-v5/en/#funding-account-ws-withdrawal-info',
}

# Method descriptions
METHOD_DESCRIPTIONS = {
    # Public endpoints
    'get_instruments': 'Retrieve a list of instruments with open contracts',
    'get_delivery_exercise_history': 'Retrieve delivery records of futures and exercise records of options',
    'get_open_interest': 'Retrieve the total open interest for contracts',
    'get_funding_rate': 'Retrieve current funding rate',
    'get_funding_rate_history': 'Retrieve funding rate history',
    'get_price_limit': 'Retrieve the highest buy limit and lowest sell limit of the instrument',
    'get_option_market_data': 'Retrieve option market data',
    'get_estimated_delivery_exercise_price': 'Retrieve estimated delivery/exercise price',
    'get_discount_rate_interest_free_quota': 'Retrieve discount rate and interest-free quota',
    'get_system_time': 'Retrieve API server time',
    'get_mark_price': 'Retrieve mark price',
    'get_position_tiers': 'Retrieve position tier information',
    'get_interest_rate_loan_quota': 'Retrieve interest rate and loan quota',
    'get_vip_interest_rate_loan_quota': 'Retrieve VIP interest rate and loan quota',
    'get_underlying': 'Retrieve the list of underlying',
    'get_insurance_fund': 'Retrieve insurance fund balance information',
    'get_unit_convert': 'Convert currency to contracts or contracts to currency',
    'get_tickers': 'Retrieve ticker information for all instruments',
    'get_index_tickers': 'Retrieve index tickers',
    'get_order_book': 'Retrieve order book of the instrument',
    'get_candlesticks': 'Retrieve candlesticks data',
    'get_candlesticks_history': 'Retrieve candlesticks history data',
    'get_index_candlesticks': 'Retrieve index candlesticks',
    'get_mark_price_candlesticks': 'Retrieve mark price candlesticks',
    'get_trades': 'Retrieve recent trades',
    'get_volume': 'Retrieve 24-hour trading volume',
    'get_oracle': 'Retrieve oracle price',
    'get_exchange_rate': 'Retrieve exchange rate',
    'get_index_components': 'Retrieve index component data',
    'get_block_tickers': 'Retrieve block trading ticker information',
    'get_block_trades': 'Retrieve block trades',

    # Trading endpoints
    'place_order': 'Place a new order',
    'place_multiple_orders': 'Place multiple orders in a batch',
    'cancel_order': 'Cancel an existing order',
    'cancel_multiple_orders': 'Cancel multiple orders in a batch',
    'amend_order': 'Modify an existing order',
    'amend_multiple_orders': 'Modify multiple orders in a batch',
    'close_positions': 'Close all positions of an instrument',
    'get_order_details': 'Retrieve order details',
    'get_order_list': 'Retrieve incomplete order list',
    'get_order_history': 'Retrieve order history (last 7 days)',
    'get_order_history_archive': 'Retrieve order history (last 3 months)',
    'get_transaction_details': 'Retrieve transaction details (last 3 days)',
    'get_transaction_history': 'Retrieve transaction history (last 3 months)',

    # Algo trading
    'place_algo_order': 'Place an algo order',
    'cancel_algo_order': 'Cancel an algo order',
    'cancel_advance_algo_order': 'Cancel advance algo order',
    'get_algo_order_list': 'Retrieve list of algo orders',
    'get_algo_order_history': 'Retrieve algo order history',

    # Account endpoints
    'get_account_balance': 'Retrieve account balance information',
    'get_positions': 'Retrieve current positions',
    'get_positions_history': 'Retrieve positions history',
    'get_account_position_risk': 'Retrieve account and position risk',
    'get_bills_details': 'Retrieve bills details (last 7 days)',
    'get_bills_archive': 'Retrieve bills details (last 3 months)',
    'get_account_config': 'Retrieve account configuration',
    'set_position_mode': 'Set position mode (long/short or net mode)',
    'set_leverage': 'Set leverage for instrument',
    'get_max_size': 'Get maximum buy/sell amount or open amount',
    'get_max_available_size': 'Get maximum available tradable amount',
    'increase_decrease_margin': 'Increase or decrease margin',
    'get_leverage': 'Get leverage information',
    'get_max_loan': 'Get maximum loan of instrument',
    'get_fee_rates': 'Get trading fee rates',
    'get_interest_accrued': 'Get interest accrued data',
    'get_interest_rate': 'Get interest rate',
    'set_greeks': 'Set Greeks display type (PA/BS)',
    'set_isolated_mode': 'Set isolated mode',
    'get_max_withdrawals': 'Get maximum withdrawals',
    'get_account_risk_state': 'Get account risk state',
    'vip_loans_borrow_repay': 'Manual borrow and repay (VIP loans)',
    'get_borrow_repay_history': 'Get borrow and repay history',
    'get_vip_interest_accrued': 'Get VIP interest accrued data',
    'get_vip_interest_deducted': 'Get VIP interest deducted data',
    'get_vip_loan_order_list': 'Get VIP loan order list',
    'get_vip_loan_order_detail': 'Get VIP loan order detail',

    # Funding endpoints
    'get_currencies': 'Retrieve list of currencies',
    'get_balance': 'Retrieve funding account balance',
    'get_account_asset_valuation': 'Get account asset valuation',
    'funds_transfer': 'Transfer funds between accounts',
    'get_funds_transfer_state': 'Get funds transfer state',
    'asset_bills_details': 'Get asset bills details',
    'lightning_deposits': 'Make lightning deposits',
    'get_deposit_address': 'Get deposit address',
    'get_deposit_history': 'Get deposit history',
    'withdrawal': 'Withdraw funds',
    'lightning_withdrawals': 'Make lightning withdrawals',
    'cancel_withdrawal': 'Cancel withdrawal',
    'get_withdrawal_history': 'Get withdrawal history',
    'small_assets_convert': 'Convert small assets',
    'get_saving_balance': 'Get saving balance',
    'savings_purchase_redemption': 'Purchase or redeem savings',
    'set_lending_rate': 'Set lending rate',
    'get_lending_history': 'Get lending history',
    'get_lending_rate_history': 'Get public borrow history',
    'get_lending_rate_summary': 'Get public borrow info',

    # Sub-account endpoints
    'get_subaccount_list': 'Get list of sub-accounts',
    'reset_subaccount_apikey': 'Reset API key of a sub-account',
    'get_subaccount_trading_balance': 'Get sub-account trading balance',
    'get_subaccount_funding_balance': 'Get sub-account funding balance',
    'subaccount_transfer': 'Transfer between sub-accounts',
    'set_permission_transfer_out': 'Set permission of transfer out',
    'get_custody_trading_subaccount_list': 'Get custody trading sub-account list',

    # Grid trading
    'place_grid_algo_order': 'Place grid algo order',
    'amend_grid_algo_order': 'Amend grid algo order',
    'stop_grid_algo_order': 'Stop grid algo order',
    'get_grid_algo_order_list': 'Get grid algo order list',
    'get_grid_algo_order_history': 'Get grid algo order history',
    'get_grid_algo_order_details': 'Get grid algo order details',
    'get_grid_algo_sub_orders': 'Get grid algo sub orders',
    'get_grid_algo_order_positions': 'Get grid algo order positions',
    'spot_moon_grid_withdraw_income': 'Withdraw income from spot moon grid',
    'compute_grid_margin_balance': 'Compute margin balance for grid',
    'adjust_grid_margin_balance': 'Adjust margin balance for grid',
    'get_grid_ai_parameter': 'Get grid AI parameter',

    # WebSocket - Public Channels
    'ws_tickers': 'Real-time ticker updates for all instruments',
    'ws_candlesticks': 'Real-time candlestick/kline data updates',
    'ws_trades': 'Real-time public trades feed',
    'ws_order_book': 'Real-time order book depth updates',
    'ws_option_trades': 'Real-time option trades feed',
    'ws_call_auction': 'Real-time call auction details',
    'ws_instruments': 'Real-time instrument information updates',
    'ws_open_interest': 'Real-time open interest data',
    'ws_funding_rate': 'Real-time funding rate updates',
    'ws_price_limit': 'Real-time price limit updates',
    'ws_option_summary': 'Real-time option summary data',
    'ws_mark_price': 'Real-time mark price updates',
    'ws_index_tickers': 'Real-time index ticker updates',
    'ws_liquidation_orders': 'Real-time liquidation order notifications',
    'ws_adl_warning': 'Real-time ADL (Auto-Deleveraging) warnings',
    'ws_economic_calendar': 'Real-time economic calendar updates',

    # WebSocket - Private Channels
    'ws_orders': 'Real-time order updates (requires authentication)',
    'ws_fills': 'Real-time trade fill notifications (requires authentication)',
    'ws_account': 'Real-time account balance updates (requires authentication)',
    'ws_positions': 'Real-time position updates (requires authentication)',
    'ws_balance_positions': 'Real-time balance and position updates (requires authentication)',
    'ws_position_risk': 'Real-time position risk warnings (requires authentication)',
    'ws_account_greeks': 'Real-time account Greeks updates (requires authentication)',
    'ws_deposit_info': 'Real-time deposit information (requires authentication)',
    'ws_withdrawal_info': 'Real-time withdrawal information (requires authentication)',
}

# Categorize methods
public_rest_methods = []
private_rest_methods = []
public_ws_methods = []
private_ws_methods = []

for method, description in METHOD_DESCRIPTIONS.items():
    if method in PUBLIC_ENDPOINTS:
        public_rest_methods.append((method, description))
    elif method in PUBLIC_WS_CHANNELS:
        public_ws_methods.append((method, description))
    elif method in PRIVATE_WS_CHANNELS:
        private_ws_methods.append((method, description))
    else:
        private_rest_methods.append((method, description))

# Generate HTML
html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OKX API v5 Methods Reference</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0052ff 0%, #00a6ff 100%);
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #0052ff 0%, #00a6ff 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .stats {
            display: flex;
            justify-content: space-around;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }

        .stat-box {
            text-align: center;
            padding: 20px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            min-width: 150px;
        }

        .stat-box .number {
            font-size: 2.5em;
            font-weight: bold;
            color: #0052ff;
            display: block;
        }

        .stat-box .label {
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .search-box {
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }

        .search-input {
            width: 100%;
            padding: 15px 20px;
            font-size: 1.1em;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.3s;
        }

        .search-input:focus {
            border-color: #0052ff;
        }

        .content {
            padding: 40px;
        }

        .section {
            margin-bottom: 50px;
        }

        .section-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px solid #e9ecef;
        }

        .section-header h2 {
            font-size: 2em;
            color: #2d3748;
        }

        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }

        .badge-public {
            background: #d4edda;
            color: #155724;
        }

        .badge-private {
            background: #fff3cd;
            color: #856404;
        }

        .badge-websocket {
            background: #e7f3ff;
            color: #004085;
        }

        .method-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
            gap: 20px;
        }

        .method-card {
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            padding: 20px;
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .method-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.1);
            border-color: #0052ff;
        }

        .method-card.public {
            border-left: 5px solid #28a745;
        }

        .method-card.private {
            border-left: 5px solid #ffc107;
        }

        .method-card.websocket {
            border-left: 5px solid #17a2b8;
        }

        .method-name {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 1.1em;
            font-weight: bold;
            color: #0052ff;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .method-icon {
            font-size: 1.2em;
        }

        .method-desc {
            color: #6c757d;
            line-height: 1.6;
            font-size: 0.95em;
            margin-bottom: 10px;
        }

        .doc-link {
            color: #0052ff;
            font-size: 0.85em;
            font-weight: 600;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #e9ecef;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .method-card:hover .doc-link {
            color: #0041cc;
        }

        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 OKX API v5 Methods Reference</h1>
            <p>Complete API Documentation for OKX Trading Platform</p>
        </div>

        <div class="stats">
            <div class="stat-box">
                <span class="number">""" + str(len(public_rest_methods)) + """</span>
                <span class="label">Public REST</span>
            </div>
            <div class="stat-box">
                <span class="number">""" + str(len(private_rest_methods)) + """</span>
                <span class="label">Private REST</span>
            </div>
            <div class="stat-box">
                <span class="number">""" + str(len(public_ws_methods)) + """</span>
                <span class="label">Public WS</span>
            </div>
            <div class="stat-box">
                <span class="number">""" + str(len(private_ws_methods)) + """</span>
                <span class="label">Private WS</span>
            </div>
            <div class="stat-box">
                <span class="number">""" + str(len(METHOD_DESCRIPTIONS)) + """</span>
                <span class="label">Total</span>
            </div>
        </div>

        <div class="search-box">
            <input type="text" class="search-input" id="searchInput" placeholder="🔍 Search methods...">
        </div>

        <div class="content">
            <!-- PUBLIC REST ENDPOINTS -->
            <div class="section">
                <div class="section-header">
                    <h2>🌐 Public REST Endpoints</h2>
                    <span class="badge badge-public">No Auth Required</span>
                </div>
                <div class="method-grid">
"""

for method, desc in sorted(public_rest_methods):
    doc_url = DOC_URL_MAP.get(method, '')
    html_content += f"""
                    <div class="method-card public" data-method="{method.lower()}" data-desc="{desc.lower()}" data-url="{doc_url}">
                        <div class="method-name">
                            <span class="method-icon">✓</span>
                            <span>{method}</span>
                        </div>
                        <div class="method-desc">{desc}</div>
                        {'<div class="doc-link">📖 Click to view documentation</div>' if doc_url else ''}
                    </div>
"""

html_content += """
                </div>
            </div>

            <!-- PRIVATE REST ENDPOINTS -->
            <div class="section">
                <div class="section-header">
                    <h2>🔐 Private REST Endpoints</h2>
                    <span class="badge badge-private">Auth Required</span>
                </div>
                <div class="method-grid">
"""

for method, desc in sorted(private_rest_methods):
    doc_url = DOC_URL_MAP.get(method, '')
    html_content += f"""
                    <div class="method-card private" data-method="{method.lower()}" data-desc="{desc.lower()}" data-url="{doc_url}">
                        <div class="method-name">
                            <span class="method-icon">🔒</span>
                            <span>{method}</span>
                        </div>
                        <div class="method-desc">{desc}</div>
                        {'<div class="doc-link">📖 Click to view documentation</div>' if doc_url else ''}
                    </div>
"""

html_content += """
                </div>
            </div>

            <!-- PUBLIC WEBSOCKET CHANNELS -->
            <div class="section">
                <div class="section-header">
                    <h2>📡 Public WebSocket Channels</h2>
                    <span class="badge badge-websocket">Real-time | No Auth</span>
                </div>
                <div class="method-grid">
"""

for method, desc in sorted(public_ws_methods):
    doc_url = DOC_URL_MAP.get(method, '')
    html_content += f"""
                    <div class="method-card websocket" data-method="{method.lower()}" data-desc="{desc.lower()}" data-url="{doc_url}">
                        <div class="method-name">
                            <span class="method-icon">📡</span>
                            <span>{method}</span>
                        </div>
                        <div class="method-desc">{desc}</div>
                        {'<div class="doc-link">📖 Click to view documentation</div>' if doc_url else ''}
                    </div>
"""

html_content += """
                </div>
            </div>

            <!-- PRIVATE WEBSOCKET CHANNELS -->
            <div class="section">
                <div class="section-header">
                    <h2>🔐 Private WebSocket Channels</h2>
                    <span class="badge badge-websocket">Real-time | Auth Required</span>
                </div>
                <div class="method-grid">
"""

for method, desc in sorted(private_ws_methods):
    doc_url = DOC_URL_MAP.get(method, '')
    html_content += f"""
                    <div class="method-card websocket" data-method="{method.lower()}" data-desc="{desc.lower()}" data-url="{doc_url}">
                        <div class="method-name">
                            <span class="method-icon">🔒📡</span>
                            <span>{method}</span>
                        </div>
                        <div class="method-desc">{desc}</div>
                        {'<div class="doc-link">📖 Click to view documentation</div>' if doc_url else ''}
                    </div>
"""

html_content += """
                </div>
            </div>
        </div>
    </div>

    <script>
        // Search functionality
        const searchInput = document.getElementById('searchInput');
        const methodCards = document.querySelectorAll('.method-card');

        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();

            methodCards.forEach(card => {
                const methodName = card.getAttribute('data-method');
                const methodDesc = card.getAttribute('data-desc');

                if (methodName.includes(searchTerm) || methodDesc.includes(searchTerm)) {
                    card.classList.remove('hidden');
                } else {
                    card.classList.add('hidden');
                }
            });
        });

        // Handle clicks - open documentation
        methodCards.forEach(card => {
            card.addEventListener('click', function(e) {
                const docUrl = this.getAttribute('data-url');

                if (docUrl) {
                    window.open(docUrl, '_blank');
                } else {
                    // Copy method name to clipboard
                    const methodName = this.querySelector('.method-name span:last-child').textContent;
                    navigator.clipboard.writeText(methodName).then(() => {
                        const originalBorder = this.style.borderColor;
                        this.style.borderColor = '#28a745';
                        setTimeout(() => {
                            this.style.borderColor = originalBorder;
                        }, 500);
                    });
                }
            });
        });
    </script>
</body>
</html>
"""

# Write HTML file
output_file = 'okx_api_methods.html'
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ Generated: {output_file}")
print(f"📊 Summary:")
print(f"   REST API: {len(public_rest_methods)} public | {len(private_rest_methods)} private")
print(f"   WebSocket: {len(public_ws_methods)} public | {len(private_ws_methods)} private")
print(f"   Total: {len(METHOD_DESCRIPTIONS)} endpoints")
print(f"\n🌐 Opening in browser...")

# Open in browser
webbrowser.open('file://' + os.path.abspath(output_file))
