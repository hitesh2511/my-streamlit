import streamlit as st
import requests
import pandas as pd
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone, time as dtime
import firebase_admin
from firebase_admin import credentials, firestore

# ---- Configuration (Edit these) -----
DELTA_API_URL = 'https://api.india.delta.exchange'
API_KEY = ''  # Your API key if any
API_SECRET = ''  # Your API secret if any
SYMBOLS = ['WLFIUSD','AIOUSD','ZORAUSD','TOWNSUSD','PROVEUSD','ENSUSD','SKLUSD','AINUSD','SAHARAUSD','HUSD','MUSD','CROSSUSD','PUMPUSD','BIDUSD','MEUSD','SOPHUSD','MASKUSD'
           ,'HYPEUSD','WCTUSD','SIGNUSD','MEMEFIUSD','DEEPUSD','INITUSD','1000XUSD','API3USD','MUBARAKUSD','BMTUSD','LAYERUSD','RAREUSD','REDUSD','AUCTIONUSD','KAITOUSD'
           ,'PIUSD','GLMUSD','TSTUSD','BAKEUSD','CAKEUSD','IPUSD','BERAUSD','VVVUSD','VINEUSD','ARCUSD','AVAAIUSD','SOLVUSD','VANAUSD','COOKIEUSD','SUSD','GRIFFAINUSD',
           'JUPUSD','SWARMSUSD','MELANIAUSD','TRUMPUSD','SPXUSD','HIVEUSD','SONICUSD','BIOUSD','MOVEUSD','PENGUUSD','AIXBTUSD','AI16ZUSD','USUALUSD','VIRTUALUSD','FARTCOINUSD',
           '1000SATSUSD','1MBABYDOGEUSD','JASMYUSD','DOGSUSD','MOODENGUSD','SUNUSD','OMUSD','IOTAUSD','RSRUSD','GOATUSD','KSMUSD','XLMUSD','SANDUSD','MANAUSD','POPCATUSD','ACTUSD',
           'PNUTUSD','SAGAUSD','NEIROUSD','POLUSD','EIGENUSD','MANTAUSD','GALAUSD','BLURUSD','OMNIUSD','TAOUSD','LISTAUSD','ZKUSD','IOUSD','ZROUSD','BBUSD','NOTUSD','ETHFIUSD','PEOPLEUSD',
           'DYDXUSD','SUSHIUSD','MKRUSD','ARUSD','RUNEUSD','XAIUSD','APTUSD','STXUSD','ALTUSD','TRXUSD','OPUSD','FILUSD','LDOUSD','ETCUSD','TRBUSD','ENAUSD','PENDLEUSD','ONDOUSD','AAVEUSD',
           'JTOUSD','HBARUSD','ORDIUSD','MEMEUSD','FLOKIUSD','PEPEUSD','ARBUSD','TIAUSD','SEIUSD','SUIUSD','WLDUSD','INJUSD','ALGOUSD','NEARUSD','ADAUSD','ATOMUSD','BONKUSD','SHIBUSD','WIFUSD',
           'DOTUSD','UNIUSD','BNBUSD','LINKUSD','LTCUSD','BCHUSD','XRPUSD','AVAXUSD','SOLUSD','DOGEUSD','ETHUSD','BTCUSD' ]  # Valid Delta Exchange symbols

 # Example shortened list
TELEGRAM_TOKEN = '7994211539:AAGTxk3VBb4rcg4CqMrK3B47geKCSjebg5w'
TELEGRAM_CHAT_ID = '-1002806176997'

# ---- Initialize Firebase from Secret File ----
secret_file_path = '/etc/secrets/streamlit-7dad6-firebase-adminsdk-fbsvc-1d4c0ac424.json'

if not firebase_admin._apps:
    cred = credentials.Certificate(secret_file_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---- Firestore helper functions ----
def get_today_date_str():
    IST = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(IST)
    return now_ist.strftime('%Y-%m-%d')

def fetch_alerted_symbols():
    doc_ref = db.collection('breakouts').document(get_today_date_str())
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {}

def mark_symbol_alerted(symbol):
    doc_ref = db.collection('breakouts').document(get_today_date_str())
    doc_ref.set({symbol: True}, merge=True)

# ---- Helper functions (same as before) ----
def generate_signature(secret, message):
    message = bytes(message, 'utf-8')
    secret = bytes(secret, 'utf-8')
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def get_headers(method='GET', path='', query_string='', payload=''):
    if not API_KEY or not API_SECRET:
        return {'User-Agent': 'python-rest-client'}
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + path + query_string + payload
    signature = generate_signature(API_SECRET, signature_data)
    return {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'python-rest-client',
        'Content-Type': 'application/json'
    }

def get_candle_1d(symbol):
    try:
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        today_midnight_ist = datetime.combine(now_ist.date(), dtime(0,0), tzinfo=IST)
        prev_day_midnight_ist = today_midnight_ist - timedelta(days=1)
        start_time_utc = int(prev_day_midnight_ist.astimezone(timezone.utc).timestamp())
        end_time_utc = int(today_midnight_ist.astimezone(timezone.utc).timestamp())
        path = '/v2/history/candles'
        query_string = f'?symbol={symbol}&resolution=1d&start={start_time_utc}&end={end_time_utc}'
        url = f"{DELTA_API_URL}{path}{query_string}"
        headers = get_headers('GET', path, query_string)
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('success') and data.get('result'):
            candle = data['result'][0]
            return float(candle['high']), float(candle['low'])
        else:
            print(f"Candle API error for {symbol}: {data}")
            return None, None
    except Exception as e:
        print(f"Error fetching candle data for {symbol}: {e}")
        return None, None

def get_latest_price(symbol):
    try:
        path = f'/v2/tickers/{symbol}'
        url = f"{DELTA_API_URL}{path}"
        headers = get_headers('GET', path)
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('success') and data.get('result'):
            return float(data['result']['mark_price'])
        else:
            print(f"Ticker API error for {symbol}: {data}")
            return None
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
        return None

def get_5min_candles(symbol, days=5):
    try:
        now = datetime.now(timezone.utc)
        end_time = int(now.timestamp())
        start_time = int((now - timedelta(days=days)).timestamp())
        path = '/v2/history/candles'
        query_string = f'?symbol={symbol}&resolution=5m&start={start_time}&end={end_time}'
        url = f"{DELTA_API_URL}{path}{query_string}"
        headers = get_headers('GET', path, query_string)
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('success') and data.get('result'):
            return data['result']
        else:
            print(f"API error for 5min candles: {data}")
            return None
    except Exception as e:
        print(f"Error fetching 5min candles: {e}")
        return None

def calc_avg_volume_5d(symbol):
    candles = get_5min_candles(symbol, days=5)
    if candles:
        volumes = [c['volume'] for c in candles if 'volume' in c]
        if volumes:
            return sum(volumes) / len(volumes)
    return None

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ---- Auto-refresh logic ----
refresh_rate = st.sidebar.slider("Auto-refresh (seconds)", 10, 600, 300)
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = time.time()
    st.session_state.has_run_once = False
current_loop_time = time.time()
if st.session_state.has_run_once:
    if current_loop_time - st.session_state.last_refresh_time > refresh_rate:
        st.session_state.last_refresh_time = current_loop_time
        st.experimental_rerun()
else:
    st.session_state.has_run_once = True

# ---- Streamlit UI -----
st.title("🚀 Delta Exchange Breakout/Breakdown Monitor")
st.write("Monitors selected coins for previous day's high/low breakouts and breakdowns with Telegram alerts.")
st.sidebar.header("Settings")

if 'breakout_time' not in st.session_state:
    st.session_state.breakout_time = {}

current_time_utc = datetime.now(timezone.utc)
IST = timezone(timedelta(hours=5, minutes=30))
current_time_ist = current_time_utc.astimezone(IST)

alerted_symbols = fetch_alerted_symbols()

table_data = []

for symbol in SYMBOLS:
    day_high, day_low = get_candle_1d(symbol)
    current_price = get_latest_price(symbol)

    if day_high is None or day_low is None or current_price is None:
        status = "Error"
        day_high = day_low = current_price = "-"
        vol_signal = "No"
        breakout_time = "-"
    else:
        if current_price > day_high:
            status = "Breakout"
        elif current_price < day_low:
            status = "Breakdown"
        else:
            status = "Normal"

        five_min_candles = get_5min_candles(symbol, days=1)
        current_5min_volume = 0
        if five_min_candles and len(five_min_candles) > 0:
            current_5min_volume = five_min_candles[-1]['volume']
        avg_5d_volume = calc_avg_volume_5d(symbol)
        vol_above_avg = False
        if current_5min_volume is not None and avg_5d_volume is not None:
            vol_above_avg = current_5min_volume > avg_5d_volume
        vol_signal = "Yes" if vol_above_avg else "No"

        alert_sent_today = alerted_symbols.get(symbol, False)

        if status in ["Breakout", "Breakdown"] and not alert_sent_today:
            avg_vol_text = f"{avg_5d_volume:.2f}" if avg_5d_volume is not None else "N/A"
            alert_msg = (
                f"🚨 {symbol} {status}!\n"
                f"💰 Price: {current_price}\n"
                f"📈 High: {day_high}\n"
                f"📉 Low: {day_low}\n"
                f"📊 5-min Volume: {current_5min_volume}\n"
                f"📉 5-day Avg Volume: {avg_vol_text}\n"
                f"⚡ Volume > 5D Avg: {vol_signal}\n"
                f"⏰ Breakout Time: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            send_telegram(alert_msg)
            mark_symbol_alerted(symbol)
            breakout_time = current_time_ist.strftime("%Y-%m-%d %H:%M:%S IST")
            st.session_state.breakout_time[symbol] = breakout_time
        else:
            if status == "Normal":
                breakout_time = "-"
                st.session_state.breakout_time[symbol] = breakout_time
            else:
                breakout_time = st.session_state.breakout_time.get(symbol, "-")

    table_data.append({
        'Symbol': symbol,
        'Price': current_price,
        '1D High': day_high,
        '1D Low': day_low,
        'Status': status,
        'Volume > 5D Avg': vol_signal,
        'Breakout Time': breakout_time
    })

df = pd.DataFrame(table_data)
pd.set_option('display.float_format', '{:.15f}'.format)
st.dataframe(df, use_container_width=True)

breakouts = len([x for x in table_data if x['Status'] == 'Breakout'])
breakdowns = len([x for x in table_data if x['Status'] == 'Breakdown'])

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Breakouts", breakouts)
with col2:
    st.metric("Breakdowns", breakdowns)
with col3:
    st.metric("Total Monitored", len(SYMBOLS))

st.info(f"Last updated: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S IST')} | Next refresh in {refresh_rate} seconds")

