class FeeTracker:
    """
    Track estimated fees and slippage to explain equity drift.
    """

    def __init__(self, taker_rate=0.0005, maker_rate=0.0002, slippage_rate=0.0002):
        self.taker_rate = taker_rate
        self.maker_rate = maker_rate
        self.slippage_rate = slippage_rate
        self.session_fees = 0.0
        self.session_slippage = 0.0
        self.session_funding = 0.0

    def estimate_order_fees(self, notional_usdt, is_maker=False):
        rate = self.maker_rate if is_maker else self.taker_rate
        return notional_usdt * rate

    def record_trade_costs(self, notional_usdt, is_maker=False):
        entry_fee = self.estimate_order_fees(notional_usdt, is_maker)
        exit_fee = self.estimate_order_fees(notional_usdt, is_maker)
        slippage = notional_usdt * self.slippage_rate * 2

        self.session_fees += entry_fee + exit_fee
        self.session_slippage += slippage

        return {
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "slippage": slippage,
            "total_costs": entry_fee + exit_fee + slippage,
        }

    def reconcile_equity_drift(self, trade_pnl, equity_change):
        difference = equity_change - trade_pnl
        known_costs = self.session_fees + self.session_slippage + self.session_funding
        unexplained = difference + known_costs
        return {
            "trade_pnl": trade_pnl,
            "equity_change": equity_change,
            "difference": difference,
            "fees": self.session_fees,
            "slippage": self.session_slippage,
            "funding": self.session_funding,
            "unexplained": unexplained,
        }

    def get_actual_fees_from_okx(self, trade_session, limit=50):
        """
        Fetch recent fees from OKX fills.
        """
        response = trade_session.get_fills(limit=limit)
        if response.get("code") != "0":
            return {"total_fees": 0.0, "breakdown": {}}

        total_fees = 0.0
        breakdown = {}

        for fill in response.get("data", []):
            fee = float(fill.get("fee") or 0.0)
            fee_ccy = fill.get("feeCcy") or "USDT"
            fee = abs(fee)
            total_fees += fee
            breakdown[fee_ccy] = breakdown.get(fee_ccy, 0.0) + fee

        return {"total_fees": total_fees, "breakdown": breakdown}
