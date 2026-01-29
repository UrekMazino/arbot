from config_execution_api import ticker_1, ticker_2, mode, depth as default_depth, inst_type, public_session
from okx.websocket.WsPublicAsync import WsPublicAsync
import asyncio
import json
from datetime import datetime
from func_log_setup import get_logger, get_log_path

# WEB SOCKET ACTIVATION
logger = get_logger(__name__)
logger.info("Logging initialized in config_ws_connect.py (file: %s)", get_log_path())

HEARTBEAT_INTERVAL = 20  # seconds


class OKXOrderbookStream:
    def __init__(self, symbols=None, depth=None, testnet=None, validate_instruments=False):
        if testnet is None:
            testnet = (mode == "demo")

        self.testnet = testnet
        self.ws_url = "wss://wspap.okx.com:8443/ws/v5/public" if testnet else "wss://ws.okx.com:8443/ws/v5/public"
        self.symbols = symbols or [ticker_1, ticker_2]
        self.depth = default_depth if depth is None else depth
        self.channel = self._select_channel(self.depth)
        self.validate_instruments = validate_instruments

        self.ws = None
        self.loop = None
        self.running = False

    @staticmethod
    def _select_channel(depth_value):
        if isinstance(depth_value, str):
            return depth_value
        return "books5" if depth_value == 5 else "books"

    def _validate_instruments(self):
        if not self.validate_instruments:
            return True

        try:
            response = public_session.get_instruments(instType=inst_type)
            if response.get("code") != "0":
                print(f"WARNING: Instrument lookup failed: {response.get('msg')}")
                return False

            valid_ids = {item.get("instId") for item in response.get("data", [])}
            missing = [symbol for symbol in self.symbols if symbol not in valid_ids]
            if missing:
                print(f"WARNING: Invalid instrument(s): {', '.join(missing)}")
                return False
        except Exception as exc:
            print(f"WARNING: Instrument validation failed: {exc}")
            return False

        return True

    def handle_message(self, msg):
        """Process incoming orderbook messages."""
        if msg == "pong":
            logger.debug("Received pong")
            return

        try:
            payload = json.loads(msg)
        except json.JSONDecodeError:
            logger.debug("Non-JSON message received: %s", msg)
            return

        if payload.get("event") == "subscribe":
            logger.info("Subscribed: %s", payload.get("arg"))
            return

        data_list = payload.get("data", [])
        if not data_list:
            return

        book = data_list[0]
        bids = book.get("bids", book.get("b", []))
        asks = book.get("asks", book.get("a", []))

        best_bid = bids[0] if bids else ["N/A", "N/A"]
        best_ask = asks[0] if asks else ["N/A", "N/A"]
        symbol = payload.get("arg", {}).get("instId", "")

        print("\n" + "=" * 60)
        print(f"Topic: {payload.get('arg', {}).get('channel')} | {symbol}")
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"Best Bid: Price={best_bid[0]}, Size={best_bid[1]}")
        print(f"Best Ask: Price={best_ask[0]}, Size={best_ask[1]}")

        if best_bid[0] != "N/A" and best_ask[0] != "N/A":
            try:
                spread = float(best_ask[0]) - float(best_bid[0])
                print(f"Spread: {spread:.6f}")
            except ValueError:
                print("Spread: N/A")

        print("=" * 60 + "\n")

    async def _send_heartbeat(self):
        while self.running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                if self.ws and self.ws.websocket:
                    await self.ws.websocket.send("ping")
                    logger.debug("Heartbeat ping sent")
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)
                break

    async def _subscribe(self):
        args = [{"channel": self.channel, "instId": symbol} for symbol in self.symbols]
        await self.ws.subscribe(args, self.handle_message)

    async def _run(self):
        await self.ws.start()

        if not self._validate_instruments():
            self.running = False
            return

        await self._subscribe()
        self.loop.create_task(self._send_heartbeat())

        print(f"OK: Connected to OKX WebSocket ({'Demo' if self.testnet else 'Live'})")
        print(f"OK: Subscribed to: {', '.join(self.symbols)} (Channel: {self.channel})")
        print(f"OK: Heartbeat every {HEARTBEAT_INTERVAL} seconds")
        print("Press Ctrl+C to stop\n")

        while self.running:
            await asyncio.sleep(1)

    async def _shutdown(self):
        if self.ws:
            await self.ws.stop()

    def start(self):
        """Start the WebSocket stream with heartbeat."""
        if self.running:
            return

        self.running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ws = WsPublicAsync(self.ws_url, debug=False)

        try:
            self.loop.run_until_complete(self._run())
        except KeyboardInterrupt:
            self.stop()
        finally:
            self.loop.run_until_complete(self._shutdown())
            self.loop.close()

    def stop(self):
        """Stop the WebSocket connection."""
        print("\nStopping WebSocket...")
        self.running = False
        logger.info("WebSocket stopped")
