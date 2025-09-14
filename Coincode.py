import streamlit as st
import requests
import pandas as pd
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from streamlit_autorefresh import st_autorefresh

# ---- Configuration (Edit these) -----
DELTA_API_URL = 'https://api.india.delta.exchange'
API_KEY = ''  # Leave empty for public data
API_SECRET = ''  # Leave empty for public data

SYMBOLS = ['WLFIUSD','AIOUSD','ZORAUSD','TOWNSUSD','PROVEUSD','ENSUSD','SKLUSD','AINUSD','SAHARAUSD','HUSD','MUSD','CROSSUSD','PUMPUSD','BIDUSD','MEUSD','SOPHUSD','MASKUSD'
           ,'HYPEUSD','WCTUSD','SIGNUSD','MEMEFIUSD','DEEPUSD','INITUSD','1000XUSD','API3USD','MUBARAKUSD','BMTUSD','LAYERUSD','RAREUSD','REDUSD','AUCTIONUSD','KAITOUSD'
           ,'PIUSD','GLMUSD','TSTUSD','BAKEUSD','CAKEUSD','IPUSD','BERAUSD','VVVUSD','VINEUSD','ARCUSD','AVAAIUSD','SOLVUSD','VANAUSD','COOKIEUSD','SUSD','GRIFFAINUSD',
           'JUPUSD','SWARMSUSD','MELANIAUSD','TRUMPUSD','SPXUSD','HIVEUSD','SONICUSD','BIOUSD','MOVEUSD','PENGUUSD','AIXBTUSD','AI16ZUSD','USUALUSD','VIRTUALUSD','FARTCOINUSD',
           '1000SATSUSD','1MBABYDOGEUSD','JASMYUSD','DOGSUSD','MOODENGUSD','SUNUSD','OMUSD','IOTAUSD','RSRUSD','GOATUSD','KSMUSD','XLMUSD','SANDUSD','MANAUSD','POPCATUSD','ACTUSD',
           'PNUTUSD','SAGAUSD','NEIROUSD','POLUSD','EIGENUSD','MANTAUSD','GALAUSD','BLURUSD','OMNIUSD','TAOUSD','LISTAUSD','ZKUSD','IOUSD','ZROUSD','BBUSD','NOTUSD','ETHFIUSD','PEOPLEUSD',
           'DYDXUSD','SUSHIUSD','MKRUSD','ARUSD','RUNEUSD','XAIUSD','APTUSD','STXUSD','ALTUSD','TRXUSD','OPUSD','FILUSD','LDOUSD','ETCUSD','TRBUSD','ENAUSD','PENDLEUSD','ONDOUSD','AAVEUSD',
           'JTOUSD','HBARUSD','ORDIUSD','MEMEUSD','FLOKIUSD','PEPEUSD','ARBUSD','TIAUSD','SEIUSD','SUIUSD','WLDUSD','INJUSD','ALGOUSD','NEARUSD','ADAUSD','ATOMUSD','BONKUSD','SHIBUSD','WIFUSD',
           'DOTUSD','UNIUSD','BNBUSD','LINKUSD','LTCUSD','BCHUSD','XRPUSD','AVAXUSD','SOLUSD','DOGEUSD','ETHUSD','BTCUSD' ]  # Valid Delta Exchange symbols


TELEGRAM_TOKEN = '7994211539:AAGTxk3VBb4rcg4CqMrK3B47geKCSjebg5w'
TELEGRAM_CHAT_ID = '-1002806176997'

# ---- Helper functions -----

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
        now = datetime.now(timezone.utc)
        today_midnight = datetime(now.year, now.month, now.day)
        prev_day_midnight = today_midnight - timedelta(days=1)

        start_time = int(prev_day_midnight.timestamp())
        end_time = int(today_midnight.timestamp())

        path = '/v2/history/candles'
        query_string = f'?symbol={symbol}&resolution=1d&start={start_time}&end={end_time}'

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

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ---- Streamlit App -----

st.title("🚀 Delta Exchange Breakout/Breakdown Monitor")
st.write("Monitors selected coins for previous day's high/low breakouts and breakdowns with Telegram alerts.")
st.sidebar.header("Settings")

refresh_rate = st.sidebar.slider("Auto-refresh (seconds)", 10, 600, 300)

count = st_autorefresh(interval=refresh_rate * 1000, key="datarefresh")

if 'last_status' not in st.session_state:
    st.session_state.last_status = {}

table_data = []

for symbol in SYMBOLS:
    day_high, day_low = get_candle_1d(symbol)
    current_price = get_latest_price(symbol)

    if day_high is None or day_low is None or current_price is None:
        status = "Error"
        day_high = day_low = current_price = "-"
    else:
        if current_price > day_high:
            status = "Breakout"
        elif current_price < day_low:
            status = "Breakdown"
        else:
            status = "Normal"

        prev_status = st.session_state.last_status.get(symbol)
        if status in ["Breakout", "Breakdown"] and prev_status != status:
            alert_msg = f"🚨 {symbol} {status}!\n💰 Price: {current_price}\n📈 High: {day_high}\n📉 Low: {day_low}"
            send_telegram(alert_msg)

        st.session_state.last_status[symbol] = status

    table_data.append({
        'Symbol': symbol,
        'Price': current_price,
        '1D High': day_high,
        '1D Low': day_low,
        'Status': status
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

st.info(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Next refresh in {refresh_rate} seconds")
