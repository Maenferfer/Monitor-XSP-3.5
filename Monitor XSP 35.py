import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="XSP 0DTE Institutional v4.4", layout="wide")

# --- FUNCIONES DE CÁLCULO ---
def calculate_rsi(series, period=14):
    if len(series) < period: return 50.0
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_noticias_tactico(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "tipo": "NORMAL", "eventos": []}
    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
            if ev.get('country') == 'US' and ev.get('impact') == 'high':
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    h_utc = datetime.strptime(ev['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    h_es = h_utc.astimezone(ZONA_HORARIA).time()
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if h_es < time(15, 30): estado["tipo"] = "PRE_MERCADO"
                    elif h_es > time(19, 30): estado["tipo"] = "TARDE_FED"
                    else: estado["bloqueo"] = True
        return estado
    except: return estado

def obtener_datos():
    tickers = {
        "XSP": "^XSP", "VIX": "^VIX", "VIX9D": "^VIX9D", 
        "VVIX": "^VVIX", "VIX1D": "^VIX1D", "NDX": "^NDX", 
        "SPY": "SPY", "SKEW": "^SKEW", "TNX": "^TNX",
        "ES_FUT": "ES=F", "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA"
    }
    vals = {}
    ahora_madrid = datetime.now(ZONA_HORARIA).time()
    mercado_abierto = time(15, 30) <= ahora_madrid <= time(22, 15)

    for k, v in tickers.items():
        try:
            df = yf.Ticker(v).history(period="1d", interval="1m")
            if df.empty:
                df = yf.Ticker(v).history(period="5d", interval="1d")
            
            if not df.empty:
                actual = float(df['Close'].iloc[-1])
                apertura = float(df['Open'].iloc[-1])
                vals[k] = {
                    "actual": actual, "apertura": apertura,
                    "min": float(df['Low'].min()), "max": float(df['High'].max()),
                    "vol_actual": float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0.0,
                    "vol_avg": float(df['Volume'].mean()) if 'Volume' in df.columns else 0.0,
                    "rsi": float(calculate_rsi(df['Close']).iloc[-1]) if k == "XSP" else 50.0,
                    "prev_close": float(df['Close'].iloc[-2]) if len(df) > 1 else actual,
                    "hist": df['Close']
                }
            else:
                vals[k] = {"actual": 0.0, "apertura": 0.0, "min": 0.0, "max": 0.0, "vol_actual": 0.0, "vol_avg": 0.0, "rsi": 50.0, "prev_close": 0.0, "hist": pd.Series()}
        except:
            vals[k] = {"actual": 0.0, "apertura": 0.0, "min": 0.0, "max": 0.0, "vol_actual": 0.0, "vol_avg": 0.0, "rsi": 50.0, "prev_close": 0.0, "hist": pd.Series()}

    # LÓGICA DE CONFLUENCIA BIG TECH (2 DE 3)
    votos_bull = 0
    for t in ["AAPL", "MSFT", "NVDA"]:
        if vals.get(t) and vals[t]["actual"] > vals[t]["apertura"]:
            votos_bull += 1
    
    confluencia_ok = (votos_bull >= 2)
    
    # SESGO HÍBRIDO
    if not mercado_abierto and vals.get("ES_FUT") and vals["ES_FUT"]["actual"] > 0:
        vals["XSP"]["hibrido_bias"] = (vals["ES_FUT"]["actual"] > vals["ES_FUT"]["apertura"]) and confluencia_ok
    else:
        vals["XSP"]["hibrido_bias"] = (vals["XSP"]["actual"] > vals["XSP"]["apertura"]) and confluencia_ok
        
    vals["XSP"]["votos_tech"] = votos_bull
    return vals

# --- INTERFAZ ---
st.title("🏛️ XSP 0DTE Institutional Terminal v4.4")

with st.sidebar:
    st.header("Configuración")
    capital = st.number_input("Capital Cuenta (€)", value=10000.0, step=500.0)
    agresividad = st.select_slider("Multiplicador Sigma", options=[1.1, 1.3, 1.5], value=1.3)
    btn_analizar = st.button("🚀 ANALIZAR MERCADO")

if btn_analizar:
    with st.spinner("Escaneando indicadores institucionales..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()
        ahora = datetime.now(ZONA_HORARIA).time()

    if d["XSP"]["actual"] == 0:
        st.error("Error de conexión. Inténtalo de nuevo.")
        st.stop()

    # --- VARIABLES ---
    xsp, ndx, spy = d["XSP"], d["NDX"], d["SPY"]
    vix, vix1d, skew = d["VIX"]["actual"], d["VIX1D"]["actual"], d["SKEW"]["actual"]
    vix_ref = vix1d if vix1d > 0 else (vix if vix > 0 else 15.0)
    
    skew_color = "normal" if skew < 135 else "off" if skew < 145 else "inverse"
    skew_msg = "BAJO ✅" if skew < 135 else "PRECAUCIÓN ⚠️" if skew < 145 else "PELIGRO CISNE NEGRO 🔥"

    vol_ratio = spy["vol_actual"] / spy["vol_avg"] if spy["vol_avg"] > 0 else 1.0
    vix_invertido = d["VIX9D"]["actual"] > vix
    bonos_subiendo = d["TNX"]["actual"] > d["TNX"]["prev_close"]

    # --- DASHBOARD ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("XSP Precio", f"{xsp['actual']:.2f}")
        st.write(f"**Tech 2/3:** {'🟢 OK' if xsp['votos_tech']>=2 else '🔴 NO'}")
    with c2:
        st.metric("Volumen SPY", f"{vol_ratio:.2f}x")
        st.write(f"**RSI:** {xsp['rsi']:.1f}")
    with c3:
        st.metric("VIX / VIX1D", f"{vix:.2f} / {vix1d:.2f}")
        st.write(f"**VIX:** {'⚠️ Invertida' if vix_invertido else '✅ Normal'}")
    with c4:
        st.metric("SKEW Index", f"{skew:.2f}", delta=skew_msg, delta_color=skew_color)
        st.write(f"**Noticias:** {'🔴 Bloqueo' if noticias['bloqueo'] else '✅ Limpio'}")

    st.divider()

    # --- TABLA Y ESTRATEGIA ---
    if noticias["bloqueo"] or (vix_invertido and skew > 148):
        st.error("### 🛑 BLOQUEO: Riesgo Crítico en el mercado.")
    else:
        # Régimen y Bias Híbrido
        std_total, std_rec = xsp["hist"].std(), xsp["hist"].tail(5).std()
        regime = "COMPRESIÓN 📉" if std_rec <= std_total else "EXPANSIÓN 📈"
        rango_pct = abs((xsp["actual"] - xsp["apertura"]) / xsp["apertura"] * 100) if xsp["apertura"] != 0 else 0.0
        cond_ic = (regime == "COMPRESIÓN 📉" and vix < 19 and vol_ratio < 1.2 and rango_pct < 0.40)
        
        bias = xsp["hibrido_bias"]
        if bonos_subiendo: bias = False 
        
        sigma = (vix_ref / 100) / (252**0.5)
        lotes = max(1, int((capital * 0.02) // 200))
        
        st.subheader("⚡ Tabla de Niveles y POP (Neto IBKR)")
        niveles = []
        for sig_mult in [1.1, 1.3, 1.5]:
            dist_t = xsp["actual"] * sigma * sig_mult
            pop = (norm.cdf(sig_mult) - norm.cdf(-sig_mult)) if cond_ic else norm.cdf(sig_mult)
            prima = max(0, ((1 - pop) * 200 * 0.65) - 1.50)
            
            label = f"Sigma {sig_mult}"
            if cond_ic:
                v_u, v_d = round(xsp["actual"] + dist_t), round(xsp["actual"] - dist_t)
                niveles.append({"Perfil": label, "POP": f"{pop*100:.1f}%", "Prima": f"{prima:.1f}€", "CALL": f"{v_u}/{v_u+2}", "PUT": f"{v_d}/{v_d-2}"})
            else:
                v = round(xsp["actual"] - dist_t) if bias else round(xsp["actual"] + dist_t)
                c = v - 2 if bias else v + 2
                niveles.append({"Perfil": label, "POP": f"{pop*100:.1f}%", "Prima": f"{prima:.1f}€", "Estrategia": "BULL PUT" if bias else "BEAR CALL", "Vender": v, "Comprar": c})
        
        st.table(pd.DataFrame(niveles))
        
        # RECOMENDACIÓN FINAL
        st.divider()
        pop_rec = (norm.cdf(agresividad) - norm.cdf(-agresividad)) if cond_ic else norm.cdf(agresividad)
        
        m1, m2 = st.columns(2)
        with m1:
            if cond_ic:
                st.success(f"### 🎯 ESTRATEGIA: IRON CONDOR ({agresividad}σ)")
            else:
                st.info(f"### 🎯 ESTRATEGIA: {'BULL PUT' if bias else 'BEAR CALL'} ({agresividad}σ)")
            st.write(f"**Probabilidad (POP):** {pop_rec*100:.1f}% | **Lotes:** {lotes}")

        with m2:
            st.warning("### 🛡️ GESTIÓN DE RIESGO")
            st.write("- **TP:** 50% de la prima.")
            st.write("- **SL:** Tocar strike vendido.")
        
        st.write(f"**Motor:** {'Híbrido (Futuros + NVDA)' if (time(9,0) <= ahora < time(15,30)) else 'RTH Live ✅'}")

else:
    st.info("Introduce capital y analiza para ver niveles de IBKR.")
        
