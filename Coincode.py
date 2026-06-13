"""
Delta Exchange – Real-Time WebSocket Monitor
============================================
Alerts via Telegram when BOTH conditions are true simultaneously:
  1. Last 2 digits of mark price fall in band: 50-60 | 90-100 | 00-10
  2. Current 5-min candle absolute % change >= 0.80%

Install deps:
    pip install websocket-client requests

Run:
    python delta_ws_monitor.py
"""

import json
import time
import threading
import requests
import websocket
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────

WEBSOCKET_URL   = "wss://socket.india.delta.exchange"
DELTA_API_URL   = "https://api.india.delta.exchange"

TELEGRAM_TOKEN = "8182445220:AAGHM9V-CBoECadOAz3SFBRTQu-gqFq8Bvs"
TELEGRAM_CHAT_ID = "-1002721557943"

CANDLE_PCT_THRESHOLD = 0.80   # minimum absolute % move on 5-min candle
ALERT_COOLDOWN_SEC   = 300    # don't re-alert same symbol within 5 minutes

# Band definitions: (low_inclusive, high_inclusive, label)
BANDS = [
    (20, 30,  "20–30"),
    (70, 80, "70–80")
    
]

SYMBOLS = [
    'WLFIUSD','AIOUSD','ZORAUSD','TOWNSUSD','PROVEUSD','ENSUSD','SKLUSD','AINUSD','SAHARAUSD','HUSD',
    'MUSD','CROSSUSD','PUMPUSD','BIDUSD','MEUSD','SOPHUSD','MASKUSD','HYPEUSD','WCTUSD','SIGNUSD',
    'MEMEFIUSD','DEEPUSD','INITUSD','1000XUSD','API3USD','MUBARAKUSD','BMTUSD','LAYERUSD','RAREUSD',
    'REDUSD','AUCTIONUSD','KAITOUSD','PIUSD','GLMUSD','TSTUSD','BAKEUSD','CAKEUSD','IPUSD','BERAUSD',
    'VVVUSD','VINEUSD','ARCUSD','AVAAIUSD','SOLVUSD','VANAUSD','COOKIEUSD','SUSD','GRIFFAINUSD',
    'JUPUSD','SWARMSUSD','MELANIAUSD','TRUMPUSD','SPXUSD','HIVEUSD','SONICUSD','BIOUSD','MOVEUSD',
    'PENGUUSD','AIXBTUSD','AI16ZUSD','USUALUSD','VIRTUALUSD','FARTCOINUSD','1000SATSUSD','1MBABYDOGEUSD',
    'JASMYUSD','DOGSUSD','MOODENGUSD','SUNUSD','OMUSD','IOTAUSD','RSRUSD','GOATUSD','KSMUSD','XLMUSD',
    'SANDUSD','MANAUSD','POPCATUSD','ACTUSD','PNUTUSD','SAGAUSD','NEIROUSD','POLUSD','EIGENUSD',
    'MANTAUSD','GALAUSD','BLURUSD','OMNIUSD','TAOUSD','LISTAUSD','ZKUSD','IOUSD','ZROUSD','BBUSD',
    'NOTUSD','ETHFIUSD','PEOPLEUSD','DYDXUSD','SUSHIUSD','MKRUSD','ARUSD','RUNEUSD','XAIUSD','APTUSD',
    'STXUSD','ALTUSD','TRXUSD','OPUSD','FILUSD','LDOUSD','ETCUSD','TRBUSD','ENAUSD','PENDLEUSD',
    'ONDOUSD','AAVEUSD','JTOUSD','HBARUSD','ORDIUSD','MEMEUSD','FLOKIUSD','PEPEUSD','ARBUSD','TIAUSD',
    'SEIUSD','SUIUSD','WLDUSD','INJUSD','ALGOUSD','NEARUSD','ADAUSD','ATOMUSD','BONKUSD','SHIBUSD',
    'WIFUSD','DOTUSD','UNIUSD','BNBUSD','LINKUSD','LTCUSD','BCHUSD','XRPUSD','AVAXUSD','SOLUSD',
    'DOGEUSD','ETHUSD','BTCUSD',
]

# ─── STATE ───────────────────────────────────────────────────────────────────

prices    = {}   # symbol → float mark price
candles   = {}   # symbol → {'open': float, 'close': float, 'pct': float}
alerted   = {}   # symbol → timestamp of last alert

lock = threading.Lock()

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def last_two_digits(price: float):
    """
    Returns last 2 digits only if integer part >= 100 (3+ digits).
    Returns None for prices < 100 like 0.11, 1.35, 25.50 — skipped.
    """
    int_part = int(price)
    if int_part < 100:  # less than 3 digits -> skip
        return None
    return int_part % 100

def in_band(last2):
    if last2 is None:
        return None
    for lo, hi, label in BANDS:
        if lo <= last2 <= hi:
            return label
    return None

def send_telegram(msg: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"  [Telegram error] {e}")

def check_and_alert(symbol: str):
    """Check both conditions and fire Telegram alert if both match."""
    with lock:
        price  = prices.get(symbol)
        candle = candles.get(symbol)

        if price is None or candle is None:
            return

        last2 = last_two_digits(price)
        band  = in_band(last2)
        pct   = candle.get('pct')

        if band is None or pct is None:
            return

        if pct < CANDLE_PCT_THRESHOLD:
            return

        # Both conditions matched — check cooldown
        now = time.time()
        last_alert = alerted.get(symbol, 0)
        if now - last_alert < ALERT_COOLDOWN_SEC:
            return

        alerted[symbol] = now

        direction = "🟢 UP" if candle['close'] >= candle['open'] else "🔴 DOWN"
        msg = (
            f"🎯 ALERT: {symbol}\n"
            f"💰 Price: {price}\n"
            f"📍 Last 2 digits: {last2:02d}  →  Band: {band}\n"
            f"📊 5m Candle: {candle['open']} → {candle['close']}  ({pct:+.2f}%)  {direction}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        print(f"\n{'='*50}")
        print(msg)
        print('='*50)
        send_telegram(msg)

# ─── WEBSOCKET HANDLERS ───────────────────────────────────────────────────────

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket connected. Subscribing to {len(SYMBOLS)} symbols...")

    # Subscribe to live mark price tickers
    ticker_sub = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": "v2/ticker",
                    "symbols": SYMBOLS
                },
                {
                    "name": "candlestick_5m",
                    "symbols": [f"MARK:{s}" for s in SYMBOLS]
                }
            ]
        }
    }
    ws.send(json.dumps(ticker_sub))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribed. Monitoring live...\n")


def on_message(ws, message):
    try:
        data = json.loads(message)
        msg_type = data.get("type", "")

        # ── Live mark price update ──
        if msg_type == "v2/ticker":
            symbol = data.get("symbol")
            mark   = data.get("mark_price")
            if symbol and mark:
                with lock:
                    prices[symbol] = float(mark)
                check_and_alert(symbol)

        # ── 5-min OHLC candle update ──
        elif msg_type == "candlestick_5m":
            # symbol comes as "MARK:BTCUSD" — strip prefix
            raw_symbol = data.get("symbol", "")
            symbol = raw_symbol.replace("MARK:", "")
            o = data.get("open")
            c = data.get("close")
            if symbol and o and c:
                open_p  = float(o)
                close_p = float(c)
                pct = abs((close_p - open_p) / open_p * 100) if open_p else 0
                with lock:
                    candles[symbol] = {
                        "open":  open_p,
                        "close": close_p,
                        "pct":   pct
                    }
                check_and_alert(symbol)

    except Exception as e:
        print(f"[Message error] {e} | raw: {message[:200]}")


def on_error(ws, error):
    print(f"[WebSocket error] {error}")


def on_close(ws, code, msg):
    print(f"[WebSocket closed] code={code} msg={msg}")
    print("Reconnecting in 5 seconds...")
    time.sleep(5)
    start_ws()


# ─── START ────────────────────────────────────────────────────────────────────

def start_ws():
    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)


if __name__ == "__main__":
    print("=" * 50)
    print("  Delta Exchange Real-Time Band Alert Monitor")
    print("=" * 50)
    print(f"  Bands monitored : 50-60 | 90-100 | 00-10")
    print(f"  Candle threshold: abs % >= {CANDLE_PCT_THRESHOLD}%  (5-min)")
    print(f"  Symbols         : {len(SYMBOLS)}")
    print(f"  Alert cooldown  : {ALERT_COOLDOWN_SEC}s per symbol")
    print("=" * 50)
    print("Press Ctrl+C to stop.\n")

    try:
        start_ws()
    except KeyboardInterrupt:
        print("\nStopped.")
