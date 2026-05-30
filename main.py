"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   ██████╗  ██████╗ ██╗     ██████╗     ██╗  ██╗                         ║
║  ██╔════╝ ██╔═══██╗██║     ██╔══██╗    ╚██╗██╔╝                         ║
║  ██║  ███╗██║   ██║██║     ██║  ██║     ╚███╔╝                          ║
║  ╚██████╔╝╚██████╔╝███████╗██████╔╝    ██╔╝ ██╗                         ║
║   ╚═════╝  ╚═════╝ ╚══════╝╚═════╝     ╚═╝  ╚═╝                         ║
║                                                                           ║
║       🥇 GOLD SUPER BOT v4.0 — ULTIMATE EDITION 🥇                      ║
║                                                                           ║
║  ✅ 1. ADX Trend Filter        ✅ 4. AI Signal Confirmation               ║
║  ✅ 2. News Calendar Filter    ✅ 5. Scalp + Swing Auto Mode              ║
║  ✅ 3. London/NY Session       ✅ 6. 3-Step Take Profit + Trailing        ║
║                                                                           ║
║  BONUS:                                                                   ║
║  ✅ 8 Indicators (RSI+MACD+BB+EMA200+ADX+Stoch+ATR+Volume)               ║
║  ✅ Discord Alerts (Signal + TP1/2/3 + SL)                               ║
║  ✅ Risk Engine (Daily Loss Limit + Position Sizing)                      ║
║  ✅ Trade Journal (CSV auto-save)                                         ║
║  ✅ Live Terminal Dashboard                                               ║
║  ✅ Breakeven SL Protection                                               ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

SETUP (run once):
  pip install yfinance pandas ta requests colorama tabulate

RUN:
  python gold_superbot_v4.py

CONFIG karo:
  1. discord_webhook  → apna Discord webhook URL paste karo
  2. anthropic_api_key → https://console.anthropic.com se free key lo (optional)
  3. paper_trading = True  → pehle paper test karo
"""

import time, datetime, requests, json, os, sys, csv
from collections import deque

# Railway/Cloud mein terminal nahi hota — colors disable
IS_CLOUD = not sys.stdout.isatty() or os.environ.get("RAILWAY_ENVIRONMENT")

# ── Library check ─────────────────────────────────────────────────────────
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    import ta
    from colorama import Fore, Style, init
    from tabulate import tabulate
    init(autoreset=True, strip=bool(IS_CLOUD))  # strip colors on Railway
except ImportError as e:
    print(f"\n❌ Missing: {e}")
    print("Run: pip install yfinance pandas ta requests colorama tabulate\n")
    sys.exit(1)


# ── Cloud Logging (replaces terminal dashboard on Railway) ──────────────────
def cloud_log(msg, level="INFO"):
    """Simple log for Railway — visible in railway.app logs panel."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO":"ℹ️ ","TRADE":"💰","SIGNAL":"📊","ERROR":"❌","TP":"🎯","WIN":"✅","LOSS":"❌"}
    print(f"[{ts}] {prefix.get(level,'  ')}{msg}", flush=True)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     ⚙️  MASTER CONFIGURATION                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
CONFIG = {

    # ─── 🔑 API Keys (set these in Railway → Variables tab) ─────────────────
    "discord_webhook":       os.environ.get("DISCORD_WEBHOOK", "YOUR_DISCORD_WEBHOOK_URL_HERE"),
    "anthropic_api_key":     os.environ.get("ANTHROPIC_API_KEY", ""),  # optional

    # ─── 📊 Market ────────────────────────────────────────────────────────
    "symbol":                "GC=F",          # Gold Futures XAU/USD
    "scalp_interval":        "5m",
    "swing_interval":        "1h",
    "lookback_scalp":        "7d",
    "lookback_swing":        "60d",

    # ─── 💰 Capital & Risk ────────────────────────────────────────────────
    "capital":               10000.0,
    "risk_per_trade_pct":    0.015,           # 1.5% risk per trade
    "max_daily_loss_pct":    0.04,            # -4% → stop trading today
    "max_open_trades":       1,

    # ─── ① ADX TREND FILTER ──────────────────────────────────────────────
    "use_adx_filter":        True,
    "adx_trending":          18,              # ADX > 18 = trending ✅ (tuned: was 22)
    "adx_strong":            30,              # ADX > 30 = very strong trend
    # Why: ADX < 22 = sideways choppy market → false signals → losses

    # ─── ② NEWS CALENDAR FILTER ──────────────────────────────────────────
    "use_news_filter":       True,
    "news_blackout_min":     60,              # Block 60min before/after news
    # High-impact events (UTC times) — bot checks these every loop
    "news_events": [
        ("13:30", "US CPI"),
        ("13:30", "US NFP Non-Farm Payrolls"),
        ("13:30", "US PPI"),
        ("13:30", "US Retail Sales"),
        ("13:30", "US GDP"),
        ("14:00", "FOMC Minutes"),
        ("18:00", "FOMC Interest Rate Decision"),
        ("18:30", "Fed Chair Press Conference"),
        ("10:00", "US ISM Manufacturing PMI"),
        ("14:30", "US Jobless Claims"),
        ("08:55", "Germany PMI"),
        ("09:00", "Eurozone CPI"),
    ],

    # ─── ③ SESSION FILTER (UTC) ──────────────────────────────────────────
    "use_session_filter":    True,
    "sessions": {
        # (start_hour, end_hour, mode, label, emoji)
        "london":   (7,  12, "SWING", "London Session 🇬🇧",   True),
        "overlap":  (13, 16, "SCALP", "London+NY Overlap 🔥",  True),  # BEST
        "newyork":  (16, 20, "SWING", "New York Session 🇺🇸",  True),
        "offhours": (20,  7, "SWING", "Off Hours 😴",           False), # no new trades
    },

    # ─── ④ AI SIGNAL CONFIRMATION ────────────────────────────────────────
    "use_ai":                True,
    "ai_min_confidence":     65,              # Reject if AI < 65% confident
    "ai_model":              "claude-haiku-4-5-20251001",  # Fast + cheap

    # ─── ⑤ SCALP vs SWING SETTINGS ───────────────────────────────────────
    # SCALP (London+NY overlap — high liquidity)
    "scalp_sl_pct":          0.003,           # 0.3% stop loss
    "scalp_tp": [
        {"level":1, "pct":0.005, "ratio":0.50, "label":"TP1"},   # +0.5% → 50%
        {"level":2, "pct":0.009, "ratio":0.30, "label":"TP2"},   # +0.9% → 30%
        {"level":3, "pct":0.014, "ratio":0.20, "label":"TP3"},   # +1.4% → 20%
    ],
    # SWING (London/NY sessions — trend following)
    "swing_sl_pct":          0.004,           # 0.4% stop loss (tuned: was 0.6% → smaller losses)
    "swing_tp": [
        {"level":1, "pct":0.010, "ratio":0.40, "label":"TP1"},   # +1.0% → 40%
        {"level":2, "pct":0.018, "ratio":0.35, "label":"TP2"},   # +1.8% → 35%
        {"level":3, "pct":0.030, "ratio":0.25, "label":"TP3"},   # +3.0% → 25%
    ],
    # R:R Summary:
    #   Scalp:  SL=-0.3%  TP1=1:1.7  TP2=1:3  TP3=1:4.7
    #   Swing:  SL=-0.6%  TP1=1:1.7  TP2=1:3  TP3=1:5.0

    # ─── ⑥ 3-STEP TP BEHAVIOR ────────────────────────────────────────────
    "move_sl_breakeven":     True,            # After TP1 → SL moves to entry
    "trailing_after_tp2":    True,            # After TP2 → trailing stop ON
    "trail_atr_mult":        1.5,             # Trail = price - (ATR × 1.5)

    # ─── 🎯 SIGNAL SENSITIVITY ───────────────────────────────────────────
    "min_score":             3,               # Out of ±10 (tuned: was 4 → more signals)
    "rsi_oversold":          32,
    "rsi_overbought":        68,

    # ─── 🔁 BOT BEHAVIOR ─────────────────────────────────────────────────
    "paper_trading":         True,            # ⚠️ ALWAYS start True!
    "check_sec":             45,              # Check every 45 seconds
    "no_repeat_min":         25,              # Don't resend same signal for 25 min
    "send_hold_discord":     False,
    "journal_file":          "trade_journal.csv",
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                      📊 GLOBAL STATE                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝
ST = {
    # Portfolio
    "cash":           CONFIG["capital"],
    "gold_units":     0.0,
    "entry_price":    0.0,
    "orig_units":     0.0,
    "sl":             0.0,
    "trailing_on":    False,
    "tp_hits":        [],
    # Stats
    "total":          0,
    "wins":           0,
    "losses":         0,
    "realized_pnl":   0.0,
    "daily_pnl":      0.0,
    "daily_date":     datetime.date.today(),
    "tp_count":       {1:0, 2:0, 3:0},
    # Session/Mode
    "mode":           "SWING",
    "session_name":   "—",
    "can_trade":      False,
    # Filter statuses (for dashboard)
    "adx_ok":         False,
    "adx_msg":        "—",
    "news_blocked":   False,
    "news_msg":       "—",
    "session_ok":     False,
    # AI
    "ai_on":          False,
    "ai_last":        "Not checked",
    "ai_conf":        0,
    # Signals
    "sig_total":      0,
    "sig_buy":        0,
    "sig_sell":       0,
}

trade_log        = []
last_signal      = None
last_signal_time = None
data_cache       = {}
price_history    = deque(maxlen=30)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         📡 FEATURE 1 — DATA ENGINE                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def fetch_data(interval):
    now = datetime.datetime.now()
    cached = data_cache.get(interval)
    if cached and (now - cached["time"]).seconds < 50:
        return cached["df"]
    try:
        period = CONFIG["lookback_scalp"] if "m" in interval else CONFIG["lookback_swing"]
        df = yf.Ticker(CONFIG["symbol"]).history(period=period, interval=interval)
        if df.empty: return data_cache.get(interval, {}).get("df")
        df = df[["Open","High","Low","Close","Volume"]].dropna()
        data_cache[interval] = {"df": df, "time": now}
        return df
    except:
        return data_cache.get(interval, {}).get("df")

def price_of(df):
    return float(df["Close"].iloc[-1]) if df is not None and not df.empty else None


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         📈 FEATURE 1 — 8 INDICATOR ENGINE                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def calc_ind(df):
    if df is None or len(df) < 60: return None
    c, h, l = df["Close"], df["High"], df["Low"]
    I = {}
    # RSI
    I["rsi"]       = round(float(ta.momentum.RSIIndicator(c,14).rsi().iloc[-1]),2)
    # MACD
    m              = ta.trend.MACD(c)
    I["macd_hist"] = round(float(m.macd_diff().iloc[-1]),4)
    I["macd"]      = round(float(m.macd().iloc[-1]),4)
    I["macd_sig"]  = round(float(m.macd_signal().iloc[-1]),4)
    # Bollinger Bands
    bb             = ta.volatility.BollingerBands(c,20,2)
    I["bb_up"]     = round(float(bb.bollinger_hband().iloc[-1]),2)
    I["bb_lo"]     = round(float(bb.bollinger_lband().iloc[-1]),2)
    I["bb_mid"]    = round(float(bb.bollinger_mavg().iloc[-1]),2)
    # EMA 20 / 50 / 200
    I["ema20"]     = round(float(ta.trend.EMAIndicator(c,20).ema_indicator().iloc[-1]),2)
    I["ema50"]     = round(float(ta.trend.EMAIndicator(c,50).ema_indicator().iloc[-1]),2)
    I["ema200"]    = round(float(ta.trend.EMAIndicator(c,min(200,len(df)-1)).ema_indicator().iloc[-1]),2)
    # ① ADX (14) — Trend Strength
    adx            = ta.trend.ADXIndicator(h,l,c,14)
    I["adx"]       = round(float(adx.adx().iloc[-1]),2)
    I["adx_pos"]   = round(float(adx.adx_pos().iloc[-1]),2)
    I["adx_neg"]   = round(float(adx.adx_neg().iloc[-1]),2)
    # Stochastic (14,3)
    st             = ta.momentum.StochasticOscillator(h,l,c,14,3)
    I["stoch_k"]   = round(float(st.stoch().iloc[-1]),2)
    I["stoch_d"]   = round(float(st.stoch_signal().iloc[-1]),2)
    # ATR (14)
    I["atr"]       = round(float(ta.volatility.AverageTrueRange(h,l,c,14).average_true_range().iloc[-1]),2)
    # Volume ratio
    vm             = df["Volume"].rolling(20).mean().iloc[-1]
    I["vol_ratio"] = round(df["Volume"].iloc[-1]/vm,2) if vm>0 else 1.0
    return I


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ① ADX TREND FILTER                                              ║
# ║         Sideways market mein trading band karo                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def adx_filter(I):
    """
    Returns (passes, message, direction)
    ADX < 22  → SIDEWAYS → block trade
    ADX 22-30 → MODERATE trend → allow with caution
    ADX > 30  → STRONG trend → best time to trade
    """
    if not CONFIG["use_adx_filter"] or I is None:
        return True, "ADX filter OFF", "ANY"

    adx = I["adx"]
    if adx < CONFIG["adx_trending"]:
        msg = f"ADX {adx:.1f} < {CONFIG['adx_trending']} → SIDEWAYS ❌ No trade"
        ST["adx_ok"] = False; ST["adx_msg"] = msg
        return False, msg, "SIDEWAYS"

    strength = "STRONG 💪" if adx > CONFIG["adx_strong"] else "MODERATE"
    dirn = "BULLISH 📈" if I["adx_pos"] > I["adx_neg"] else "BEARISH 📉"
    msg  = f"ADX {adx:.1f} → {strength} {dirn} ✅"
    ST["adx_ok"] = True; ST["adx_msg"] = msg
    return True, msg, dirn


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ② NEWS CALENDAR FILTER                                          ║
# ║         High-impact news events se 60 min pehle/baad skip               ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def news_filter():
    """
    Returns (blocked, reason)
    Checks current UTC time against all configured news events.
    Production upgrade: connect to ForexFactory API for live calendar.
    """
    if not CONFIG["use_news_filter"]:
        ST["news_blocked"] = False; ST["news_msg"] = "News filter OFF"
        return False, "News filter OFF"

    now     = datetime.datetime.utcnow()
    now_m   = now.hour * 60 + now.minute
    blk     = CONFIG["news_blackout_min"]

    for t_str, name in CONFIG["news_events"]:
        h, m   = map(int, t_str.split(":"))
        evt_m  = h*60 + m
        diff   = abs(now_m - evt_m)
        if diff <= blk:
            direction = "baad" if now_m > evt_m else "pehle"
            msg = f"📰 {name} — {diff}min {direction} [BLACKOUT] ❌"
            ST["news_blocked"] = True; ST["news_msg"] = msg
            return True, msg

    msg = "✅ No news events — clear to trade"
    ST["news_blocked"] = False; ST["news_msg"] = msg
    return False, msg


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ③ SESSION FILTER                                                ║
# ║         London / NY / Overlap — sahi waqt par hi trade                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def session_filter():
    """
    Returns (can_trade, mode, session_label)
    London+NY overlap (13-16 UTC) → SCALP mode 🔥
    London / NY alone → SWING mode
    Off hours → no new trades
    """
    if not CONFIG["use_session_filter"]:
        ST["session_ok"] = True; ST["session_name"] = "All Hours"
        return True, "SWING", "All Hours (filter OFF)"

    hour = datetime.datetime.utcnow().hour

    # Overlap check first (most important)
    s_lo, s_hi, mode, label, ok = CONFIG["sessions"]["overlap"]
    if s_lo <= hour < s_hi:
        ST["session_ok"] = True; ST["session_name"] = label; ST["mode"] = mode
        return True, mode, label

    for key in ["london", "newyork", "offhours"]:
        s_lo, s_hi, mode, label, ok = CONFIG["sessions"][key]
        if key == "offhours":
            in_session = hour >= s_lo or hour < s_hi
        else:
            in_session = s_lo <= hour < s_hi
        if in_session:
            ST["session_ok"] = ok; ST["session_name"] = label; ST["mode"] = mode
            return ok, mode, label

    ST["session_ok"] = False; ST["session_name"] = "Unknown"
    return False, "SWING", "Unknown"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         🎯 8-FACTOR SIGNAL ENGINE                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def signal_engine(price, I):
    """
    8 indicators × weighted scoring:
    ① RSI        ② MACD      ③ EMA trend   ④ EMA200 (macro)
    ⑤ Bollinger  ⑥ Stoch     ⑦ ADX dir     ⑧ Volume
    Max: +10  Min: -10
    BUY if ≥ min_score, SELL if ≤ -min_score
    """
    if I is None: return "HOLD", 0, []
    score, reasons = 0, []

    # ① RSI (weight 2)
    if   I["rsi"] < CONFIG["rsi_oversold"]:  score+=2; reasons.append(f"🟢 RSI Oversold {I['rsi']}")
    elif I["rsi"] < 40:                       score+=1; reasons.append(f"🟡 RSI Low {I['rsi']}")
    elif I["rsi"] > CONFIG["rsi_overbought"]: score-=2; reasons.append(f"🔴 RSI Overbought {I['rsi']}")
    elif I["rsi"] > 60:                       score-=1; reasons.append(f"🟠 RSI High {I['rsi']}")

    # ② MACD Histogram (weight 1)
    if I["macd_hist"]>0: score+=1; reasons.append(f"🟢 MACD Bullish +{I['macd_hist']}")
    else:                score-=1; reasons.append(f"🔴 MACD Bearish {I['macd_hist']}")

    # ③ EMA 20/50 Short Trend (weight 1)
    if I["ema20"]>I["ema50"]: score+=1; reasons.append("🟢 EMA20 > EMA50 (uptrend)")
    else:                     score-=1; reasons.append("🔴 EMA20 < EMA50 (downtrend)")

    # ④ EMA200 Macro Trend (weight 1)
    if price>I["ema200"]: score+=1; reasons.append(f"🟢 Above EMA200 ${I['ema200']:,.0f} (bull)")
    else:                 score-=1; reasons.append(f"🔴 Below EMA200 ${I['ema200']:,.0f} (bear)")

    # ⑤ Bollinger Bands (weight 2)
    if   price<=I["bb_lo"]:  score+=2; reasons.append(f"🟢 BB Lower bounce ${price:.0f} ≤ ${I['bb_lo']:.0f}")
    elif price>=I["bb_up"]:  score-=2; reasons.append(f"🔴 BB Upper reject ${price:.0f} ≥ ${I['bb_up']:.0f}")

    # ⑥ Stochastic (weight 1)
    if   I["stoch_k"]<20 and I["stoch_k"]>I["stoch_d"]: score+=1; reasons.append(f"🟢 Stoch oversold+cross K={I['stoch_k']}")
    elif I["stoch_k"]>80 and I["stoch_k"]<I["stoch_d"]: score-=1; reasons.append(f"🔴 Stoch overbought+cross K={I['stoch_k']}")

    # ⑦ ADX direction (weight 1)
    if I["adx_pos"]>I["adx_neg"]: score+=1; reasons.append(f"🟢 +DI {I['adx_pos']:.0f} > -DI {I['adx_neg']:.0f}")
    else:                         score-=1; reasons.append(f"🔴 -DI {I['adx_neg']:.0f} > +DI {I['adx_pos']:.0f}")

    # ⑧ Volume confirmation (weight 1)
    if I["vol_ratio"]>1.3:
        bonus = +1 if score>0 else -1
        score+=bonus; reasons.append(f"{'🟢' if bonus>0 else '🔴'} High volume {I['vol_ratio']}x avg confirms")

    ST["sig_total"]+=1
    if   score>=CONFIG["min_score"]:  ST["sig_buy"]+=1;  return "BUY",  score, reasons
    elif score<=-CONFIG["min_score"]: ST["sig_sell"]+=1; return "SELL", score, reasons
    return "HOLD", score, reasons


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ④ AI SIGNAL CONFIRMATION                                        ║
# ║         Claude AI se final trade confirm karao                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def ai_confirm(signal, price, I, reasons, mode):
    """
    Sends signal data to Claude AI for confirmation.
    Returns (approved, confidence%, reason_text)
    Falls back gracefully if API key missing or error.
    """
    if not CONFIG["use_ai"]:
        return True, 80, "AI disabled in config"

    key = CONFIG["anthropic_api_key"]
    if not key or "YOUR_" in key:
        ST["ai_on"] = False
        return True, 75, "No API key → auto-approved"

    try:
        prompt = f"""You are a professional Gold (XAU/USD) trading analyst.

A trading bot wants to place a {signal} trade on Gold at ${price:,.2f}.
Trading mode: {mode}

Live Indicators:
  RSI(14)      = {I['rsi']}   {'← oversold' if I['rsi']<35 else '← overbought' if I['rsi']>65 else ''}
  MACD Hist    = {I['macd_hist']}   {'← bullish' if I['macd_hist']>0 else '← bearish'}
  ADX          = {I['adx']}   {'← strong trend' if I['adx']>25 else '← weak/sideways'}
  BB Upper/Low = ${I['bb_up']:.2f} / ${I['bb_lo']:.2f}
  EMA 20/50    = ${I['ema20']:.2f} / ${I['ema50']:.2f}
  EMA 200      = ${I['ema200']:.2f}
  Stoch K/D    = {I['stoch_k']} / {I['stoch_d']}
  Volume Ratio = {I['vol_ratio']}x average

Bot signal reasons (top 4):
{chr(10).join(reasons[:4])}

Should this {signal} be executed? Reply ONLY in JSON:
{{"confirmed":true/false,"confidence":0-100,"reason":"one sentence max"}}"""

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":key,"anthropic-version":"2023-06-01","content-type":"application/json"},
            json={"model":CONFIG["ai_model"],"max_tokens":120,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=10
        )
        if r.status_code == 200:
            txt  = r.json()["content"][0]["text"].strip()
            txt  = txt.replace("```json","").replace("```","").strip()
            data = json.loads(txt)
            conf = int(data.get("confidence",50))
            rsn  = data.get("reason","—")
            ok   = data.get("confirmed",False) and conf>=CONFIG["ai_min_confidence"]
            ST["ai_on"]=True; ST["ai_last"]=rsn; ST["ai_conf"]=conf
            return ok, conf, rsn
        else:
            ST["ai_on"]=False
            return True, 70, f"API error {r.status_code} → auto-approved"
    except Exception as e:
        ST["ai_on"]=False
        return True, 70, f"AI unavailable → auto-approved ({str(e)[:30]})"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ⑤ SCALP + SWING MODE — Position & Risk Engine                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def get_tp_config(mode):
    return CONFIG["scalp_tp"] if mode=="SCALP" else CONFIG["swing_tp"]

def get_sl_pct(mode):
    return CONFIG["scalp_sl_pct"] if mode=="SCALP" else CONFIG["swing_sl_pct"]

def calc_units(price, mode):
    sl_dist   = price * get_sl_pct(mode)
    risk_usd  = ST["cash"] * CONFIG["risk_per_trade_pct"]
    units     = risk_usd / sl_dist if sl_dist>0 else 0
    max_units = ST["cash"]*0.95/price
    return round(min(units, max_units),4)

def daily_limit_hit():
    if ST["daily_date"] != datetime.date.today():
        ST["daily_pnl"]=0.0; ST["daily_date"]=datetime.date.today()
    return ST["daily_pnl"] < -(CONFIG["capital"]*CONFIG["max_daily_loss_pct"])


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         AUTO TRADE EXECUTION                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def do_buy(price, mode, reasons, ai_rsn=""):
    if ST["gold_units"]>0: return None
    units = calc_units(price, mode)
    cost  = units*price
    if cost>ST["cash"] or units<=0: return None

    sl = round(price*(1-get_sl_pct(mode)),2)
    tps= get_tp_config(mode)
    tp_prices = [round(price*(1+s["pct"]),2) for s in tps]

    ST["cash"]        -= cost
    ST["gold_units"]   = units; ST["orig_units"]  = units
    ST["entry_price"]  = price; ST["sl"]          = sl
    ST["trailing_on"]  = False; ST["tp_hits"]     = []
    ST["total"]       += 1;    ST["mode"]         = mode

    t = {"id":ST["total"],"mode":mode,"entry":price,"units":units,"sl":sl,
         "tp1":tp_prices[0],"tp2":tp_prices[1],"tp3":tp_prices[2],
         "time":datetime.datetime.now().strftime("%H:%M:%S"),
         "status":"OPEN","pnl":0.0,"tp_closed":[],"ai":ai_rsn}
    trade_log.append(t)
    save_journal(t, "OPEN")
    return t

def do_close(price, reason="SIGNAL"):
    if ST["gold_units"]<=0: return 0
    pnl = ST["gold_units"]*(price-ST["entry_price"])
    ST["cash"]+=ST["gold_units"]*price; ST["realized_pnl"]+=pnl; ST["daily_pnl"]+=pnl
    if pnl>=0: ST["wins"]+=1
    else:      ST["losses"]+=1
    ct = next((t for t in reversed(trade_log) if t["status"]=="OPEN"),None)
    if ct:
        ct["status"]="WIN ✅" if pnl>=0 else "LOSS ❌"
        ct["exit_price"]=price; ct["pnl"]=round(pnl,2)
        save_journal(ct,"CLOSE")
    ST["gold_units"]=0; ST["tp_hits"]=[]; ST["trailing_on"]=False
    return pnl


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         ⑥ 3-STEP TAKE PROFIT ENGINE                                     ║
# ║         TP1→Breakeven SL  TP2→Trailing Stop  TP3→Full Run              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def process_tps(price, I):
    """
    Every loop:
    1. Update trailing stop if active
    2. Check each TP level — partial close on hit
    3. Move SL to breakeven after TP1
    4. Activate trailing stop after TP2
    5. Check SL hit — full close
    6. If all 3 TPs done — close remainder
    Returns list of events for Discord alerts
    """
    if ST["gold_units"]<=0: return []
    ct = next((t for t in reversed(trade_log) if t["status"]=="OPEN"),None)
    if not ct: return []

    atr    = I["atr"] if I else 2.0
    events = []
    tps    = get_tp_config(ST["mode"])

    # Step 1: Update trailing SL
    if ST["trailing_on"]:
        new_sl = round(price - atr*CONFIG["trail_atr_mult"],2)
        if new_sl > ST["sl"]:
            ST["sl"] = new_sl; ct["sl"] = new_sl

    # Step 2-4: TP checks
    for step in tps:
        lvl = step["level"]
        if lvl in ST["tp_hits"]: continue
        tp_p = ct[f"tp{lvl}"]
        if price >= tp_p:
            close_u = min(ST["orig_units"]*step["ratio"], ST["gold_units"])
            pnl     = close_u*(price-ST["entry_price"])
            ST["cash"]+=close_u*price; ST["gold_units"]-=close_u
            ST["realized_pnl"]+=pnl;  ST["daily_pnl"]+=pnl
            ST["tp_hits"].append(lvl); ST["tp_count"][lvl]+=1
            ct["tp_closed"].append({"lvl":lvl,"price":price,"pnl":round(pnl,2)})
            events.append({"type":f"TP{lvl}","price":price,"pnl":round(pnl,2),"units":close_u})

            # TP1 → move SL to breakeven
            if lvl==1 and CONFIG["move_sl_breakeven"]:
                ST["sl"]=ST["entry_price"]; ct["sl"]=ST["entry_price"]
                events[-1]["note"] = "SL → Breakeven ✅"

            # TP2 → activate trailing stop
            if lvl==2 and CONFIG["trailing_after_tp2"]:
                ST["trailing_on"]=True
                events[-1]["note"] = "Trailing Stop ACTIVE 📡"

    # Step 5: SL hit
    if price<=ST["sl"] and ST["gold_units"]>0:
        pnl = ST["gold_units"]*(price-ST["entry_price"])
        ST["cash"]+=ST["gold_units"]*price; ST["realized_pnl"]+=pnl; ST["daily_pnl"]+=pnl
        if pnl>=0: ST["wins"]+=1
        else:      ST["losses"]+=1
        ct["status"]="WIN ✅" if pnl>=0 else "LOSS ❌"
        ct["exit_price"]=price; ct["pnl"]=round(pnl,2)
        ST["gold_units"]=0; ST["tp_hits"]=[]; ST["trailing_on"]=False
        events.append({"type":"SL","price":price,"pnl":round(pnl,2)})
        save_journal(ct,"CLOSE")

    # Step 6: All TPs done → close remainder
    if len(ST["tp_hits"])==3 and ST["gold_units"]>0:
        pnl = ST["gold_units"]*(price-ST["entry_price"])
        ST["cash"]+=ST["gold_units"]*price; ST["realized_pnl"]+=pnl; ST["daily_pnl"]+=pnl
        ST["wins"]+=1; ST["gold_units"]=0
        ct["status"]="🏆 ALL TPs WIN"; ct["exit_price"]=price
        ct["pnl"]=round(pnl+sum(x["pnl"] for x in ct["tp_closed"]),2)
        ST["tp_hits"]=[]; ST["trailing_on"]=False
        events.append({"type":"ALL_TP","price":price,"pnl":round(pnl,2)})
        save_journal(ct,"CLOSE")

    return events


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         📋 TRADE JOURNAL (CSV)                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def save_journal(trade, action):
    file = CONFIG["journal_file"]
    exists = os.path.isfile(file)
    try:
        with open(file,"a",newline="") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["datetime","action","mode","entry","exit","units","sl","tp1","tp2","tp3","pnl","status","ai"])
            w.writerow([
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                action, trade.get("mode","—"),
                trade.get("entry","—"), trade.get("exit_price","—"),
                trade.get("units","—"), trade.get("sl","—"),
                trade.get("tp1","—"), trade.get("tp2","—"), trade.get("tp3","—"),
                trade.get("pnl","—"), trade.get("status","—"),
                trade.get("ai","—")[:60]
            ])
    except: pass


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         📨 DISCORD ALERTS                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def _discord(embed):
    url = CONFIG["discord_webhook"]
    if "YOUR_DISCORD" in url: return
    try: requests.post(url,json={"embeds":[embed]},timeout=8)
    except: pass

def discord_signal(sig, price, score, I, reasons, trade=None, ai_conf=None, ai_rsn=""):
    c  = {"BUY":0x00FF7F,"SELL":0xFF3333,"HOLD":0x888888}
    em = {"BUY":"🟢 📈","SELL":"🔴 📉","HOLD":"⚪"}
    now= datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode = ST["mode"]

    fields=[
        {"name":"💰 XAU/USD",      "value":f"**${price:,.2f}**",         "inline":True},
        {"name":"📊 Score",        "value":f"**{score:+d}/±10**",         "inline":True},
        {"name":"🎯 Mode",         "value":f"`{mode}`",                   "inline":True},
    ]
    if trade:
        tp_cfg = get_tp_config(mode)
        fields+=[
            {"name":f"🛡️ Stop Loss",          "value":f"`${trade['sl']:,.2f}`",  "inline":True},
            {"name":f"🎯 TP1 {int(tp_cfg[0]['ratio']*100)}% (+{tp_cfg[0]['pct']*100:.1f}%)",
                                               "value":f"`${trade['tp1']:,.2f}`", "inline":True},
            {"name":f"🎯 TP2 {int(tp_cfg[1]['ratio']*100)}% (+{tp_cfg[1]['pct']*100:.1f}%)",
                                               "value":f"`${trade['tp2']:,.2f}`", "inline":True},
            {"name":f"🏆 TP3 {int(tp_cfg[2]['ratio']*100)}% (+{tp_cfg[2]['pct']*100:.1f}%)",
                                               "value":f"`${trade['tp3']:,.2f}`", "inline":True},
        ]
    if ai_conf:
        ok_em = "✅" if ai_conf>=65 else "⚠️"
        fields.append({"name":f"🤖 AI {ok_em} {ai_conf}%","value":ai_rsn[:70],"inline":False})

    fields+=[
        {"name":"📉 RSI/ADX/Stoch", "value":f"`{I['rsi']}` / `{I['adx']}` / `{I['stoch_k']}`","inline":True},
        {"name":"📈 MACD Hist",     "value":f"`{I['macd_hist']}`",          "inline":True},
        {"name":"🔍 Reasons",       "value":"\n".join(reasons[:4]),          "inline":False},
    ]
    _discord({"title":f"{em[sig]}  GOLD SIGNAL: **{sig}**","color":c[sig],
              "fields":fields,"footer":{"text":f"🥇 Gold SuperBot v4  •  {now}  •  {'📄Paper' if CONFIG['paper_trading'] else '💵LIVE'}"}})

def discord_tp(ev, entry):
    t,p,pnl = ev["type"],ev["price"],ev["pnl"]
    titles  = {"TP1":"🎯 TP1 HIT — Breakeven SL set!","TP2":"🎯 TP2 HIT — Trailing Stop ON!",
               "TP3":"🏆 TP3 HIT — Max profit!","SL":"🔴 STOP LOSS HIT","ALL_TP":"🏆 ALL TPs DONE!"}
    colors  = {"TP1":0x00CCFF,"TP2":0x00FF99,"TP3":0xFFD700,"SL":0xFF3333,"ALL_TP":0xFFD700}
    now     = datetime.datetime.now().strftime("%H:%M:%S")
    note    = ev.get("note","")
    _discord({"title":titles.get(t,t),"color":colors.get(t,0xFFFFFF),
              "fields":[{"name":"💰 Price","value":f"`${p:,.2f}`","inline":True},
                        {"name":"📥 Entry","value":f"`${entry:,.2f}`","inline":True},
                        {"name":"💹 PnL","value":f"**${pnl:+.2f}**","inline":True},
                        {"name":"📌 Note","value":note or "—","inline":False}],
              "footer":{"text":f"🥇 Gold SuperBot v4  •  {now}"}})


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║         🖥️  SUPER DASHBOARD                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def dashboard(price, sig, score, I):
    os.system("cls" if os.name=="nt" else "clear")
    now   = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    total = ST["cash"] + ST["gold_units"]*price
    roi   = (total-CONFIG["capital"])/CONFIG["capital"]*100
    unr   = (price-ST["entry_price"])*ST["gold_units"] if ST["gold_units"]>0 else 0
    wrate = ST["wins"]/ST["total"]*100 if ST["total"]>0 else 0
    sc    = Fore.GREEN if sig=="BUY" else (Fore.RED if sig=="SELL" else Fore.CYAN)
    rc    = Fore.GREEN if roi>=0 else Fore.RED

    print(Fore.YELLOW+Style.BRIGHT+"""
╔═══════════════════════════════════════════════════════════════════════════╗
║  ██████╗  ██████╗ ██╗     ██████╗    ██╗  ██╗  GOLD SUPER BOT v4.0     ║
║ ██╔════╝ ██╔═══██╗██║     ██╔══██╗   ╚██╗██╔╝  XAU/USD ULTIMATE        ║
║ ██║  ███╗██║   ██║██║     ██║  ██║    ╚███╔╝   6 Filters + AI          ║
║ ╚██████╔╝╚██████╔╝███████╗██████╔╝   ██╔╝ ██╗  8 Indicators            ║
╚═══════════════════════════════════════════════════════════════════════════╝""")

    print(f"\n  ⏰ {now}   💰 {Fore.WHITE}${price:,.2f}{Fore.RESET}/oz   {sc}{sig} ({score:+d}/±10){Style.RESET_ALL}")
    print(f"  📍 {ST['session_name']}   Mode: {Fore.CYAN}{ST['mode']}{Fore.RESET}   {'📄 Paper' if CONFIG['paper_trading'] else Fore.RED+'💵 LIVE'}")

    # ── 6 Filters Status ──
    all_ok = ST["session_ok"] and not ST["news_blocked"] and ST["adx_ok"] and not daily_limit_hit()
    print(f"\n{Fore.CYAN}  🔍 ALL 6 FILTERS {'✅ ALL CLEAR — READY TO TRADE' if all_ok else '⚠️  BLOCKED'}")
    f_rows = [
        ["①","ADX Trend",      (Fore.GREEN if ST["adx_ok"] else Fore.RED)+ST["adx_msg"][:55]],
        ["②","News Calendar",  (Fore.RED if ST["news_blocked"] else Fore.GREEN)+ST["news_msg"][:55]],
        ["③","Session",        (Fore.GREEN if ST["session_ok"] else Fore.RED)+ST["session_name"]],
        ["④","AI Confirm",     (Fore.GREEN if ST["ai_on"] else Fore.YELLOW)+
                                (f"ACTIVE ✅ (last: {ST['ai_conf']}%)" if ST["ai_on"] else "Key not set ⚠️")],
        ["⑤","Scalp/Swing",   Fore.CYAN+f"Mode: {ST['mode']} (auto-selected by session)"],
        ["⑥","3-Step TP",     Fore.GREEN+f"TP1→BEP SL  TP2→Trailing  TP3→Full Run ✅"],
    ]
    print(tabulate(f_rows, headers=["#","Filter","Status"], tablefmt="simple"))

    # ── Portfolio ──
    print(f"\n{Fore.CYAN}  💼 PORTFOLIO")
    print(tabulate([
        ["💵 Cash",         f"${ST['cash']:,.2f}"],
        ["🥇 Gold Units",   f"{ST['gold_units']:.4f} oz"],
        ["📊 Total Value",  f"${total:,.2f}"],
        ["📈 Unrealized",   (Fore.GREEN if unr>=0 else Fore.RED)+f"${unr:+.2f}"],
        ["💹 Realized PnL", (Fore.GREEN if ST['realized_pnl']>=0 else Fore.RED)+f"${ST['realized_pnl']:+.2f}"],
        ["📅 Today",        (Fore.GREEN if ST['daily_pnl']>=0 else Fore.RED)+f"${ST['daily_pnl']:+.2f}"],
        ["📉 Total ROI",    rc+f"{roi:+.2f}%"],
        ["🏆 Win Rate",     (Fore.GREEN if wrate>=50 else Fore.RED)+f"{wrate:.0f}%  ({ST['wins']}W/{ST['losses']}L/{ST['total']} total)"],
        ["🎯 TP Hits",      f"TP1:{ST['tp_count'][1]}  TP2:{ST['tp_count'][2]}  TP3:{ST['tp_count'][3]}"],
    ], tablefmt="simple"))

    # ── Active Trade ──
    if ST["gold_units"]>0:
        ct = next((t for t in reversed(trade_log) if t["status"]=="OPEN"),None)
        if ct:
            tpc = get_tp_config(ST["mode"])
            print(f"\n{Fore.YELLOW}  ⚡ ACTIVE {ct['mode']} TRADE")
            print(tabulate([
                ["Entry",                  f"${ct['entry']:,.2f}"],
                ["Units",                  f"{ct['units']:.4f} oz"],
                ["🛡️ SL",                 Fore.RED+f"${ST['sl']:,.2f}"+(" 📡 Trailing" if ST["trailing_on"] else "")],
                [f"⑥TP1 {int(tpc[0]['ratio']*100)}%",  Fore.CYAN+f"${ct['tp1']:,.2f}"+(" ✅" if 1 in ST["tp_hits"] else "")],
                [f"⑥TP2 {int(tpc[1]['ratio']*100)}%",  Fore.CYAN+f"${ct['tp2']:,.2f}"+(" ✅" if 2 in ST["tp_hits"] else "")],
                [f"⑥TP3 {int(tpc[2]['ratio']*100)}%",  Fore.YELLOW+f"${ct['tp3']:,.2f}"+(" ✅" if 3 in ST["tp_hits"] else "")],
                ["🤖 AI",                  ct.get("ai","—")[:55]],
            ], tablefmt="simple"))

    # ── 8 Indicators ──
    if I:
        print(f"\n{Fore.CYAN}  📊 8 INDICATORS")
        rc2 = Fore.GREEN if I['rsi']<38 else (Fore.RED if I['rsi']>62 else Fore.WHITE)
        mc  = Fore.GREEN if I['macd_hist']>0 else Fore.RED
        ac  = Fore.GREEN if I['adx']>25 else Fore.YELLOW
        print(tabulate([
            ["① RSI(14)",       rc2+str(I['rsi'])],
            ["② MACD Hist",     mc+str(I['macd_hist'])],
            ["③ EMA 20/50",     f"${I['ema20']:,.0f} / ${I['ema50']:,.0f}"],
            ["④ EMA 200",       f"${I['ema200']:,.0f}"],
            ["⑤ BB Up/Lo",      f"${I['bb_up']:,.2f} / ${I['bb_lo']:,.2f}"],
            ["⑥ Stoch K/D",     f"{I['stoch_k']} / {I['stoch_d']}"],
            ["⑦ ADX/+DI/-DI",  ac+f"{I['adx']} / {I['adx_pos']} / {I['adx_neg']}"],
            ["⑧ Vol Ratio",     (Fore.GREEN if I['vol_ratio']>1.2 else Fore.WHITE)+f"{I['vol_ratio']}x"],
        ], tablefmt="simple"))

    # ── AI last decision ──
    print(f"\n  🤖 AI: {Fore.CYAN}{ST['ai_last'][:70]}")

    # ── Recent trades ──
    closed = [t for t in reversed(trade_log) if t["status"]!="OPEN"][:4]
    if closed:
        print(f"\n{Fore.CYAN}  📋 RECENT TRADES")
        rows=[[t["time"],t["mode"],f"${t['entry']:,.0f}",
               f"${t.get('exit_price',0):,.0f}" if "exit_price" in t else "—",
               (Fore.GREEN if t.get("pnl",0)>=0 else Fore.RED)+f"${t.get('pnl',0):+.2f}",
               t["status"]] for t in closed]
        print(tabulate(rows,headers=["Time","Mode","Entry","Exit","PnL","Result"],tablefmt="simple"))

    if daily_limit_hit():
        print(Fore.RED+"\n  ⛔ DAILY LOSS LIMIT HIT — No new trades today!")

    print(f"\n{'─'*75}")
    print(f"  ⏳ Next: {CONFIG['check_sec']}s  |  Journal: {CONFIG['journal_file']}  |  Ctrl+C to stop")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                        🚀 MAIN LOOP                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
def run():
    global last_signal, last_signal_time

    print(Fore.YELLOW+Style.BRIGHT+"""
╔═══════════════════════════════════════════════════════════════════════════╗
║        🥇 GOLD SUPER BOT v4.0 — Initializing...                         ║
║                                                                           ║
║   Filter 1: ADX Trend Filter ............... LOADING                     ║
║   Filter 2: News Calendar Filter ........... LOADING                     ║
║   Filter 3: London/NY Session Filter ....... LOADING                     ║
║   Filter 4: AI Signal Confirmation ......... LOADING                     ║
║   Filter 5: Scalp + Swing Auto Mode ........ LOADING                     ║
║   Filter 6: 3-Step Take Profit Engine ...... LOADING                     ║
╚═══════════════════════════════════════════════════════════════════════════╝
""")
    time.sleep(2)

    while True:
        now = datetime.datetime.now()

        # ── ③ Session check ──
        can_trade, mode, session = session_filter()

        # ── Fetch data for active mode ──
        interval = CONFIG["scalp_interval"] if mode=="SCALP" else CONFIG["swing_interval"]
        df    = fetch_data(interval)
        price = price_of(df)

        if price is None:
            print(Fore.RED+f"[{now.strftime('%H:%M:%S')}] No price — retry 30s...")
            time.sleep(30); continue

        price_history.append(price)

        # ── Indicators ──
        I = calc_ind(df)

        # ── ① ADX Filter ──
        adx_ok, adx_msg, adx_dir = adx_filter(I)

        # ── ② News Filter ──
        news_block, news_msg = news_filter()

        # ── Manage existing trade ──
        entry_snap = ST["entry_price"]
        events = process_tps(price, I) if ST["gold_units"]>0 else []
        for ev in events:
            print(Fore.MAGENTA+f"  [{ev['type']}] ${ev['price']:,.2f}  PnL:${ev['pnl']:+.2f}  {ev.get('note','')}")
            discord_tp(ev, entry_snap)

        # ── Signal ──
        sig, score, reasons = signal_engine(price, I)

        # ── All filters must pass for new trade ──
        all_clear = can_trade and not news_block and adx_ok and not daily_limit_hit()

        # ── Execute ──
        if CONFIG["paper_trading"] and sig in ["BUY","SELL"]:

            if sig=="BUY" and ST["gold_units"]==0 and all_clear:
                # ④ AI Confirmation
                ai_ok, ai_conf, ai_rsn = ai_confirm(sig, price, I, reasons, mode)
                ST["ai_last"]=ai_rsn; ST["ai_conf"]=ai_conf
                if ai_ok:
                    trade = do_buy(price, mode, reasons, ai_rsn)
                    if trade:
                        discord_signal(sig,price,score,I,reasons,trade,ai_conf,ai_rsn)
                        last_signal,last_signal_time = sig,now
                        print(Fore.GREEN+f"  ✅ BUY ${price:,.2f} | {mode} | AI:{ai_conf}% | {trade['units']:.4f}oz")
                    cloud_log(f"BUY EXECUTED @ ${price:,.2f} | Mode:{mode} | AI:{ai_conf}% | Units:{trade['units']:.4f}", "TRADE")
                else:
                    ST["ai_last"]=f"❌ REJECTED ({ai_conf}%): {ai_rsn}"
                    print(Fore.YELLOW+f"  🤖 AI REJECTED ({ai_conf}%): {ai_rsn[:50]}")

            elif sig=="SELL" and ST["gold_units"]>0 and all_clear:
                ai_ok, ai_conf, ai_rsn = ai_confirm(sig, price, I, reasons, mode)
                ST["ai_last"]=ai_rsn; ST["ai_conf"]=ai_conf
                if ai_ok:
                    pnl = do_close(price, "SELL SIGNAL")
                    discord_signal(sig,price,score,I,reasons,ai_conf=ai_conf,ai_rsn=ai_rsn)
                    last_signal,last_signal_time = sig,now
                    print((Fore.GREEN if pnl>=0 else Fore.RED)+f"  {'✅' if pnl>=0 else '❌'} SELL ${price:,.2f} PnL:${pnl:+.2f}")

            elif sig!="HOLD" and all_clear:
                no_rep = (last_signal!=sig or not last_signal_time or
                          (now-last_signal_time).seconds > CONFIG["no_repeat_min"]*60)
                if no_rep and (CONFIG["send_hold_discord"] or sig!="HOLD"):
                    discord_signal(sig,price,score,I,reasons)
                    last_signal,last_signal_time = sig,now

        # Cloud log (visible in Railway logs)
        if IS_CLOUD:
            val  = ST["cash"] + ST["gold_units"]*price
            roi  = (val - CONFIG["capital"]) / CONFIG["capital"] * 100
            unr  = (price - ST["entry_price"]) * ST["gold_units"] if ST["gold_units"]>0 else 0
            cloud_log(f"XAU/USD ${price:,.2f} | {sig} ({score:+d}) | Mode:{ST['mode']} | ROI:{roi:+.2f}%", "SIGNAL")
            if ST["gold_units"]>0:
                cloud_log(f"OPEN TRADE: Entry ${ST['entry_price']:,.2f} | Unrealized ${unr:+.2f} | SL ${ST['sl']:,.2f}", "TRADE")
            cloud_log(f"Filters: ADX={'✅' if ST['adx_ok'] else '❌'} News={'❌' if ST['news_blocked'] else '✅'} Session={'✅' if ST['session_ok'] else '❌'}", "INFO")
        else:
            dashboard(price, sig, score, I)
        time.sleep(CONFIG["check_sec"])


# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        total_v = ST["cash"] + ST["gold_units"]*0
        wr = ST["wins"]/ST["total"]*100 if ST["total"]>0 else 0
        print(Fore.YELLOW+f"""
╔═════════════════════════════════════════╗
║    🥇 GOLD SUPER BOT v4.0 — Summary    ║
╠═════════════════════════════════════════╣
║  Realized PnL : ${ST['realized_pnl']:>+10.2f}           ║
║  Today PnL    : ${ST['daily_pnl']:>+10.2f}           ║
║  Total Trades : {ST['total']:<6}                     ║
║  Win Rate     : {wr:.0f}%  ({ST['wins']}W / {ST['losses']}L)          ║
║  TP1 Hits     : {ST['tp_count'][1]:<6}                     ║
║  TP2 Hits     : {ST['tp_count'][2]:<6}                     ║
║  TP3 Hits     : {ST['tp_count'][3]:<6}                     ║
║  Journal      : trade_journal.csv ✅   ║
╚═════════════════════════════════════════╝
  Allah Hafiz! Trade safely! 🙏
""")
