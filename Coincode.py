"""
Delta Exchange - Real-Time WebSocket Monitor
=============================================
Alert logic:
  1. 5-min candle absolute % change >= 0.80%
  2. Candle's open OR close (or both) fall in a price band (last 2 digits)
     Bands: 50-60 | 90-100 | 00-10
  Alert types:
    - ENTRY: open was outside band, close entered band
    - EXIT:  open was inside band, close exited band
    - INSIDE: both open & close in band (strong move within band)

Install: pip install websocket-client requests
Run:     python delta_ws_monitor.py
"""

import json
import time
import threading
import requests
import websocket
from datetime import datetime
import streamlit as st

# --- CONFIG ------------------------------------------------------------------

WEBSOCKET_URL    = "wss://socket.india.delta.exchange"
DELTA_API_URL    = "https://api.india.delta.exchange"

TELEGRAM_TOKEN = st.secrets["BOT_ID"]
TELEGRAM_CHAT_ID = st.secrets["BOT"]

CANDLE_PCT_THRESHOLD = 0.6   # minimum absolute % move on 5-min candle
ALERT_COOLDOWN_SEC   = 300    # seconds before re-alerting same symbol

# Band definitions: (low_inclusive, high_inclusive, label)
# Based on last 2 digits of integer part of price
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

# --- STATE -------------------------------------------------------------------

prices  = {}   # symbol -> float mark price
candles = {}   # symbol -> {open, close, pct}
alerted = {}   # symbol -> last alert timestamp

lock = threading.Lock()

# --- HELPERS -----------------------------------------------------------------

def last_two_digits(price: float):
    """
    Returns last 2 digits of integer part only if price >= 100 (3+ digit integer).
    Returns None for prices like 0.11, 1.35, 25.50 -- skipped entirely.
    """
    int_part = int(price)
    if int_part < 100:
        return None
    return int_part % 100

def in_band(last2):
    """Return band label if last2 is in any defined band, else None."""
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
    """
    Alert when:
      - 5min candle % >= threshold (0.80%)  -- checked FIRST
      - AND candle's open OR close falls in a price band
        * ENTRY:  open outside band, close inside band
        * EXIT:   open inside band, close outside band
        * INSIDE: both open & close inside band (strong move within zone)
    """
    with lock:
        price  = prices.get(symbol)
        candle = candles.get(symbol)

        if price is None or candle is None:
            return

        open_p  = candle.get('open')
        close_p = candle.get('close')
        pct     = candle.get('pct')

        if open_p is None or close_p is None or pct is None:
            return

        # Condition 1: candle % must meet threshold
        if pct < CANDLE_PCT_THRESHOLD:
            return

        # Condition 2: check bands on open and close
        open_last2  = last_two_digits(open_p)
        close_last2 = last_two_digits(close_p)

        open_band  = in_band(open_last2)
        close_band = in_band(close_last2)

        # At least one of open/close must touch a band
        if open_band is None and close_band is None:
            return

        # Cooldown -- avoid spamming same symbol
        now = time.time()
        if now - alerted.get(symbol, 0) < ALERT_COOLDOWN_SEC:
            return

        alerted[symbol] = now

        # Determine alert type
        if open_band is None and close_band is not None:
            alert_type = f"ENTRY into {close_band}"
            band_info  = (f"Open last2: {open_last2:02d} (outside) -> "
                          f"Close last2: {close_last2:02d} (band {close_band})")
        elif open_band is not None and close_band is None:
            alert_type = f"EXIT from {open_band}"
            band_info  = (f"Open last2: {open_last2:02d} (band {open_band}) -> "
                          f"Close last2: {close_last2:02d} (outside)")
        else:
            alert_type = f"STRONG MOVE in {close_band}"
            band_info  = (f"Open last2: {open_last2:02d} -> "
                          f"Close last2: {close_last2:02d} (band {close_band})")

        direction = "UP" if close_p >= open_p else "DOWN"
        msg = (
            f"[ALERT] {alert_type}: {symbol}\n"
            f"Price: {price}\n"
            f"{band_info}\n"
            f"5m Candle: {open_p} -> {close_p}  ({pct:+.2f}%)  {direction}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        print(f"\n{'='*50}")
        print(msg)
        print('='*50)
        send_telegram(msg)

# --- WEBSOCKET HANDLERS ------------------------------------------------------

def on_open(ws):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket connected. Subscribing to {len(SYMBOLS)} symbols...")
    sub = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {"name": "v2/ticker",      "symbols": SYMBOLS},
                {"name": "candlestick_5m", "symbols": [f"MARK:{s}" for s in SYMBOLS]}
            ]
        }
    }
    ws.send(json.dumps(sub))
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Subscribed. Monitoring live...\n")

def on_message(ws, message):
    try:
        data = json.loads(message)
        msg_type = data.get("type", "")

        if msg_type == "v2/ticker":
            symbol = data.get("symbol")
            mark   = data.get("mark_price")
            if symbol and mark:
                with lock:
                    prices[symbol] = float(mark)
                check_and_alert(symbol)

        elif msg_type == "candlestick_5m":
            symbol = data.get("symbol", "").replace("MARK:", "")
            o = data.get("open")
            c = data.get("close")
            if symbol and o and c:
                open_p  = float(o)
                close_p = float(c)
                pct = abs((close_p - open_p) / open_p * 100) if open_p else 0
                with lock:
                    candles[symbol] = {"open": open_p, "close": close_p, "pct": pct}
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

# --- START -------------------------------------------------------------------

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
    print(f"  Bands         : 50-60 | 90-100 | 00-10")
    print(f"  Alert on      : ENTRY, EXIT, STRONG MOVE in band")
    print(f"  Candle thresh : abs % >= {CANDLE_PCT_THRESHOLD}% (5-min)")
    print(f"  Symbols       : {len(SYMBOLS)}")
    print(f"  Cooldown      : {ALERT_COOLDOWN_SEC}s per symbol")
    print("=" * 50)
    print("Press Ctrl+C to stop.\n")
    try:
        start_ws()
    except KeyboardInterrupt:
        print("\nStopped.")
