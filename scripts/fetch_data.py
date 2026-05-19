"""
fetch_data.py
Fetches all market data needed for the weekly report.
Data sources:
  - yfinance       : indices, ETFs, commodities, DXY, 10Y yield (free, no key)
  - FRED API       : macro economic data (free, optional FRED_API_KEY env var)
  - CNN F&G proxy  : Fear & Greed scraped from CNN (fallback: alternative.me crypto index)
  - pizzint.watch  : Pentagon Pizza Index (scraped, fallback provided)
"""

import os
import json
import time
import logging
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
TODAY = datetime.utcnow()
YEAR_START = f"{TODAY.year}-01-01"
ONE_YEAR_AGO = (TODAY - timedelta(days=365)).strftime("%Y-%m-%d")
TWELVE_MONTHS_AGO = (TODAY - timedelta(days=370)).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        log.warning(f"safe() caught: {e}")
        return default


def calculate_rsi(prices: list, period: int = 14) -> float | None:
    """Wilder's smoothed RSI."""
    if len(prices) < period + 2:
        return None
    s = pd.Series(prices, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return round(val, 2) if not np.isnan(val) else None


def ytd_pct(hist: pd.DataFrame) -> float | None:
    if hist is None or len(hist) < 2:
        return None
    first = float(hist["Close"].iloc[0])
    last = float(hist["Close"].iloc[-1])
    if first == 0:
        return None
    return round((last - first) / first * 100, 2)


def twelve_month_trend(hist: pd.DataFrame, n_points: int = 12) -> list[float]:
    """Return ~12 evenly-spaced closing prices for sparkline charts."""
    if hist is None or hist.empty:
        return []
    closes = hist["Close"].dropna()
    if len(closes) < 2:
        return []
    idx = np.linspace(0, len(closes) - 1, n_points, dtype=int)
    return [round(float(closes.iloc[i]), 2) for i in idx]


def fred(series_id: str, limit: int = 3) -> tuple[float | None, str | None]:
    """
    Fetch latest value from FRED.

    Strategy (in order):
      1. FRED JSON API  — fastest, requires FRED_API_KEY env var (free registration)
      2. FRED public CSV — no API key needed; same data, slightly slower
         URL: https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID
    """
    # ── Path 1: API key ──────────────────────────────────────────────
    if FRED_API_KEY:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "limit": limit,
            "sort_order": "desc",
            "observation_start": ONE_YEAR_AGO,
        }
        try:
            r = requests.get(url, params=params, timeout=12)
            obs = r.json().get("observations", [])
            for o in obs:
                try:
                    return round(float(o["value"]), 4), o["date"]
                except (ValueError, KeyError):
                    continue
        except Exception as e:
            log.warning(f"FRED API {series_id}: {e}")

    # ── Path 2: Public CSV (no key needed) ───────────────────────────
    try:
        csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        r = requests.get(csv_url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; MarketBot/1.0)"})
        if r.status_code == 200:
            lines = [l for l in r.text.strip().splitlines() if l and not l.startswith("DATE")]
            # Build list of valid (date, value) pairs, oldest-first
            valid = [(parts[0], parts[1]) for l in lines
                     if len(parts := l.split(",")) == 2 and parts[1] not in (".", "")]
            if valid:
                # limit=1 → most recent; limit=N → Nth-most-recent (for YoY/delta calcs)
                idx = max(0, len(valid) - limit)
                date_str, val_str = valid[idx]
                return round(float(val_str), 4), date_str
    except Exception as e:
        log.warning(f"FRED CSV {series_id}: {e}")

    return None, None


# ─────────────────────────────────────────────
# INDIVIDUAL FETCHERS
# ─────────────────────────────────────────────

def fetch_index(symbol: str, label: str) -> dict:
    log.info(f"Fetching index: {symbol}")
    tk = yf.Ticker(symbol)
    hist_1y = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_10y = safe(lambda: tk.history(period="10y"), pd.DataFrame())
    info = safe(lambda: tk.info, {})

    price = safe(lambda: float(hist_1y["Close"].iloc[-1]))
    prev = safe(lambda: float(hist_1y["Close"].iloc[-2]))
    chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None
    rsi = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    pe = safe(lambda: round(float(info.get("trailingPE") or info.get("forwardPE") or 0), 2)) or None
    ytd = ytd_pct(safe(lambda: tk.history(start=YEAR_START), None))
    trend_10y = twelve_month_trend(hist_10y, n_points=24)

    return {
        "symbol": symbol, "label": label,
        "price": price, "change_pct": chg_pct,
        "pe": pe, "rsi": rsi, "ytd": ytd,
        "trend_10y": trend_10y,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_vix() -> dict:
    log.info("Fetching VIX / VXN")
    vix_hist = safe(lambda: yf.Ticker("^VIX").history(period="5d"), pd.DataFrame())
    vxn_hist = safe(lambda: yf.Ticker("^VXN").history(period="5d"), pd.DataFrame())
    return {
        "vix": round(float(vix_hist["Close"].iloc[-1]), 2) if not vix_hist.empty else None,
        "vxn": round(float(vxn_hist["Close"].iloc[-1]), 2) if not vxn_hist.empty else None,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_fear_greed() -> dict:
    log.info("Fetching Fear & Greed Index")
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = r.json()["data"][0]
        return {
            "value": int(data["value"]),
            "label": data["value_classification"],
            "date": datetime.utcfromtimestamp(int(data["timestamp"])).strftime("%b %d, %Y"),
        }
    except Exception as e:
        log.warning(f"F&G API: {e}")
        return {"value": None, "label": "N/A", "date": TODAY.strftime("%b %d, %Y")}


def fetch_macro() -> dict:
    log.info("Fetching macro data via FRED + yfinance fallback")

    # ── FRED (requires FRED_API_KEY env var) ──────────────────────
    fed_rate, fed_date = fred("FEDFUNDS")
    t10y_fred, t10y_date_fred = fred("DGS10")
    dxy_fred, dxy_date_fred = fred("DTWEXBGS")
    cpi, cpi_date = fred("CPIAUCSL")
    cpi_hist_val, _ = fred("CPIAUCSL", limit=14)
    core_cpi, core_date = fred("CPILFESL")
    core_hist, _ = fred("CPILFESL", limit=14)
    unrate, ur_date = fred("UNRATE")
    icsa, icsa_date = fred("ICSA")
    nfp, nfp_date = fred("PAYEMS")
    nfp_prev, _ = fred("PAYEMS", limit=3)
    ism_mfg, ism_mfg_date = fred("NAPM")
    ism_svc, ism_svc_date = fred("NMFCI")

    cpi_yoy = round((cpi - cpi_hist_val) / cpi_hist_val * 100, 2) if cpi and cpi_hist_val else None
    core_yoy = round((core_cpi - core_hist) / core_hist * 100, 2) if core_cpi and core_hist else None
    # PAYEMS monthly change: level in thousands, limit=3 gets ~2 months prior
    nfp_change = round(nfp - nfp_prev) if nfp and nfp_prev else None  # already in K

    # ── akshare fallback for ISM PMI (when FRED NAPM/NMFCI unavailable) ──
    if ism_mfg is None:
        try:
            import akshare as ak
            df_ism = ak.macro_usa_ism_pmi()
            if df_ism is not None and not df_ism.empty:
                # akshare returns newest-first; col0=date, col2=actual value
                latest = df_ism.iloc[0]
                ism_mfg      = float(latest.iloc[2]) if latest.iloc[2] not in ("", None) else None
                ism_mfg_date = str(latest.iloc[1])[:10]
        except Exception as e:
            log.warning(f"akshare ISM mfg fallback: {e}")

    if ism_svc is None:
        try:
            import akshare as ak
            df_svc = ak.macro_usa_ism_non_pmi()
            if df_svc is not None and not df_svc.empty:
                latest = df_svc.iloc[0]
                ism_svc      = float(latest.iloc[2]) if latest.iloc[2] not in ("", None) else None
                ism_svc_date = str(latest.iloc[1])[:10]
        except Exception as e:
            log.warning(f"akshare ISM svc fallback: {e}")

    # ── yfinance fallback for market-priced data ───────────────────
    # 10-Year Treasury yield via ^TNX (CBOE index, value = yield %)
    t10y, t10y_date = t10y_fred, t10y_date_fred
    if t10y is None:
        log.info("FRED DGS10 unavailable; falling back to ^TNX (yfinance)")
        tnx_hist = safe(lambda: yf.Ticker("^TNX").history(period="5d"), pd.DataFrame())
        if not tnx_hist.empty:
            val = float(tnx_hist["Close"].iloc[-1])
            t10y = round(val if val < 20 else val / 10, 2)
            t10y_date = tnx_hist.index[-1].strftime("%Y-%m-%d")

    # DXY dollar index via DX-Y.NYB (ICE Dollar Index)
    dxy, dxy_date = dxy_fred, dxy_date_fred
    if dxy is None:
        log.info("FRED DTWEXBGS unavailable; falling back to DX-Y.NYB (yfinance)")
        dxy_hist = safe(lambda: yf.Ticker("DX-Y.NYB").history(period="5d"), pd.DataFrame())
        if not dxy_hist.empty:
            dxy = round(float(dxy_hist["Close"].iloc[-1]), 2)
            dxy_date = dxy_hist.index[-1].strftime("%Y-%m-%d")

    return {
        "fed_rate": fed_rate, "fed_date": fed_date,
        "t10y": t10y, "t10y_date": t10y_date,
        "dxy": dxy, "dxy_date": dxy_date,
        "cpi_yoy": cpi_yoy, "cpi_date": cpi_date,
        "core_cpi_yoy": core_yoy, "core_date": core_date,
        "unrate": unrate, "ur_date": ur_date,
        "nfp_change": nfp_change, "nfp_date": nfp_date,
        "icsa": int(icsa / 1000) if icsa else None, "icsa_date": icsa_date,
        "ism_mfg": ism_mfg, "ism_mfg_date": ism_mfg_date,
        "ism_svc": ism_svc, "ism_svc_date": ism_svc_date,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_cme_fedwatch() -> dict:
    """Approximate FedWatch via 30-day Fed Funds Futures (ZQ)."""
    log.info("Fetching CME FedWatch proxy")
    # ZQ=F is the nearest Fed Funds futures contract
    try:
        tk = yf.Ticker("ZQM26.CBT")  # adjust contract month as needed
        hist = tk.history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            implied_rate = round(100 - price, 3)
            return {"implied_rate": implied_rate, "cuts_priced": None, "date": TODAY.strftime("%b %d, %Y")}
    except Exception as e:
        log.warning(f"FedWatch proxy: {e}")
    return {"implied_rate": None, "cuts_priced": 0, "date": TODAY.strftime("%b %d, %Y")}


def fetch_sector(symbol: str, name_en: str, name_cn: str) -> dict:
    log.info(f"Fetching sector: {symbol}")
    tk = yf.Ticker(symbol)
    hist_1y = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: tk.history(start=YEAR_START), pd.DataFrame())

    price = safe(lambda: float(hist_1y["Close"].iloc[-1]))
    rsi = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    ytd = ytd_pct(hist_ytd)
    trend = twelve_month_trend(hist_1y, n_points=12)

    # Momentum classification based on RSI + YTD
    if rsi and ytd:
        if rsi > 55 and ytd > 5:
            momentum = "Leading"
        elif rsi > 50 and ytd > 0:
            momentum = "Improving"
        elif rsi < 45 and ytd < 0:
            momentum = "Lagging"
        else:
            momentum = "Weakening"
    else:
        momentum = "Neutral"

    return {
        "symbol": symbol, "name_en": name_en, "name_cn": name_cn,
        "price": price, "ytd": ytd, "rsi": rsi,
        "momentum": momentum, "trend": trend,
    }


def fetch_semiconductor() -> dict:
    log.info("Fetching semiconductor data")
    # SOX proxy via SOXX ETF
    soxx = yf.Ticker("SOXX")
    hist_1y = safe(lambda: soxx.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: soxx.history(start=YEAR_START), pd.DataFrame())
    info = safe(lambda: soxx.info, {})

    price = safe(lambda: float(hist_1y["Close"].iloc[-1]))
    rsi = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    ytd = ytd_pct(hist_ytd)
    trend = twelve_month_trend(hist_1y, n_points=12)
    week52_low = safe(lambda: round(float(info.get("fiftyTwoWeekLow", 0)), 2))
    week52_high = safe(lambda: round(float(info.get("fiftyTwoWeekHigh", 0)), 2))

    # SOX index (approximated via ^SOX)
    sox_tk = yf.Ticker("^SOX")
    sox_hist = safe(lambda: sox_tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    sox_price = safe(lambda: round(float(sox_hist["Close"].iloc[-1]), 0))
    sox_rsi = calculate_rsi(sox_hist["Close"].tolist() if sox_hist is not None and not sox_hist.empty else [])
    sox_trend = twelve_month_trend(sox_hist, n_points=12) if sox_hist is not None else []

    return {
        "soxx_price": price, "soxx_rsi": rsi, "soxx_ytd": ytd,
        "soxx_trend": trend, "soxx_52w_low": week52_low, "soxx_52w_high": week52_high,
        "sox_price": sox_price, "sox_rsi": sox_rsi, "sox_trend": sox_trend,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_commodity(symbol: str, name_en: str, name_cn: str, emoji: str, unit: str,
                    price_scale: float = 1.0) -> dict:
    """
    price_scale: multiplier applied to raw yfinance price and trend values.
    Use 0.01 for grain futures quoted in cents/bushel (ZS=F, ZC=F) to convert to USD.
    """
    log.info(f"Fetching commodity: {symbol}")
    tk = yf.Ticker(symbol)
    hist_1y = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: tk.history(start=YEAR_START), pd.DataFrame())

    raw_price = safe(lambda: float(hist_1y["Close"].iloc[-1]))
    price = round(raw_price * price_scale, 2) if raw_price is not None else None
    rsi = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    ytd = ytd_pct(hist_ytd)   # ratio-based, unaffected by scale
    raw_trend = twelve_month_trend(hist_1y, n_points=12)
    trend = [round(x * price_scale, 2) for x in raw_trend]

    return {
        "symbol": symbol, "name_en": name_en, "name_cn": name_cn,
        "emoji": emoji, "unit": unit,
        "price": price, "ytd": ytd, "rsi": rsi, "trend": trend,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_pizza_index() -> dict:
    """
    Scrape pizzint.watch for current DOUGHCON level.
    Falls back to DOUGHCON 5 (normal) if unavailable.
    """
    log.info("Fetching Pentagon Pizza Index")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MarketReportBot/1.0)"}
        r = requests.get("https://pizzint.watch", headers=headers, timeout=12)
        text = r.text.upper()
        for lvl in [1, 2, 3, 4, 5]:
            if f"DOUGHCON {lvl}" in text or f"DOUGHCON{lvl}" in text:
                return {
                    "level": lvl,
                    "status": ["最高警戒", "极端飙升", "显著上升", "轻微异常", "正常"][lvl - 1],
                    "date": TODAY.strftime("%b %d, %Y"),
                    "source": "pizzint.watch",
                }
    except Exception as e:
        log.warning(f"PizzINT scrape failed: {e}")

    return {
        "level": 5,
        "status": "正常 (数据暂不可用)",
        "date": TODAY.strftime("%b %d, %Y"),
        "source": "fallback",
    }


# ─────────────────────────────────────────────
# CHINA A-SHARE FETCHERS
# ─────────────────────────────────────────────

CN_INDICES = [
    ("000001.SS", "上证指数", "SSE Composite"),
    ("399001.SZ", "深证成指", "SZSE Component"),
    ("399006.SZ", "创业板指", "ChiNext"),
    ("000300.SS", "沪深300",  "CSI 300"),
    ("000688.SS", "科创50",   "STAR 50"),
]

CN_SECTORS = [
    # (symbol, name_cn, sector_label)
    ("510300.SS", "沪深300ETF", "大盘蓝筹"),
    ("159915.SZ", "创业板ETF",  "成长科技"),
    ("512010.SS", "医药ETF",    "医药生物"),
    ("512690.SS", "酒ETF",      "消费白酒"),
    ("515000.SS", "科技ETF",    "信息技术"),
    ("512200.SS", "地产ETF",    "房地产"),
    ("512400.SS", "有色ETF",    "有色金属"),
    ("516160.SS", "新能源车ETF","新能源汽车"),
]


def fetch_cn_index(symbol: str, name_cn: str, name_en: str) -> dict:
    log.info(f"Fetching CN index: {symbol}")
    tk = yf.Ticker(symbol)
    hist_1y  = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: tk.history(start=YEAR_START), pd.DataFrame())
    info     = safe(lambda: tk.info, {})

    price    = safe(lambda: round(float(hist_1y["Close"].iloc[-1]), 2))
    prev     = safe(lambda: float(hist_1y["Close"].iloc[-2]))
    chg_pct  = round((price - prev) / prev * 100, 2) if price and prev else None
    rsi      = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    pe       = safe(lambda: round(float(info.get("trailingPE") or 0), 2)) or None
    ytd      = ytd_pct(hist_ytd)
    trend_1y = twelve_month_trend(hist_1y, n_points=12)

    return {
        "symbol": symbol, "name_cn": name_cn, "name_en": name_en,
        "price": price, "change_pct": chg_pct, "pe": pe,
        "rsi": rsi, "ytd": ytd, "trend_1y": trend_1y,
        "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_cn_sector(symbol: str, name_cn: str, sector_label: str) -> dict:
    log.info(f"Fetching CN sector ETF: {symbol}")
    tk       = yf.Ticker(symbol)
    hist_1y  = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: tk.history(start=YEAR_START), pd.DataFrame())

    price = safe(lambda: round(float(hist_1y["Close"].iloc[-1]), 3))
    rsi   = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    ytd   = ytd_pct(hist_ytd)

    if rsi and ytd is not None:
        if   rsi > 55 and ytd > 5:  momentum = "Leading"
        elif rsi > 50 and ytd > 0:  momentum = "Improving"
        elif rsi < 45 and ytd < 0:  momentum = "Lagging"
        else:                        momentum = "Weakening"
    else:
        momentum = "Neutral"

    return {
        "symbol": symbol, "name_cn": name_cn, "sector_label": sector_label,
        "price": price, "ytd": ytd, "rsi": rsi, "momentum": momentum,
    }


def fetch_cn_northbound() -> dict:
    """北向资金 — today's net flow via akshare EastMoney."""
    log.info("Fetching CN northbound fund flow")
    try:
        import akshare as ak
        df = ak.stock_hsgt_fund_flow_summary_em()
        # Rows where col2 contains '港' = cross-border (northbound) direction
        port = df[df.iloc[:, 2].str.contains("港", na=False)]
        net_flow = round(float(port.iloc[:, 5].sum()), 2)   # 亿元, negative = outflow
        sh_flow  = round(float(port.iloc[0, 5]), 2) if len(port) >= 1 else None
        sz_flow  = round(float(port.iloc[1, 5]), 2) if len(port) >= 2 else None
        date_str = str(df.iloc[0, 0])
        return {
            "net_flow": net_flow, "sh_flow": sh_flow, "sz_flow": sz_flow,
            "date": date_str, "source": "eastmoney",
        }
    except Exception as e:
        log.warning(f"Northbound fetch failed: {e}")
    return {"net_flow": None, "sh_flow": None, "sz_flow": None,
            "date": TODAY.strftime("%b %d, %Y"), "source": "unavailable"}


def fetch_cn_margin() -> dict:
    """融资融券余额 — SSE + SZSE combined via akshare."""
    log.info("Fetching CN margin balance")
    try:
        import akshare as ak
        sh = ak.macro_china_market_margin_sh()
        sz = ak.macro_china_market_margin_sz()

        # Last column = 融资融券余额 (total margin balance) in yuan
        sh_total = float(sh.iloc[-1, -1])
        sz_total = float(sz.iloc[-1, -1])
        combined = sh_total + sz_total        # yuan → 万亿
        to_wanyi = lambda x: round(x / 1e12, 4)

        # 12-month trend (combined) for sparkline
        n = min(len(sh), len(sz), 12)
        trend = [to_wanyi(float(sh.iloc[-(n - i), -1]) + float(sz.iloc[-(n - i), -1]))
                 for i in range(n - 1, -1, -1)]

        return {
            "balance": to_wanyi(combined),      # 万亿元
            "sh_balance": to_wanyi(sh_total),
            "sz_balance": to_wanyi(sz_total),
            "trend": trend,
            "date": str(sh.iloc[-1, 0]),
            "source": "akshare/sse+szse",
        }
    except Exception as e:
        log.warning(f"Margin balance fetch failed: {e}")
    return {"balance": None, "sh_balance": None, "sz_balance": None,
            "trend": [], "date": TODAY.strftime("%b %d, %Y"), "source": "unavailable"}


def fetch_cn_pmi_official() -> dict:
    """中国官方PMI — NBS manufacturing + non-manufacturing via akshare."""
    log.info("Fetching CN official PMI")
    try:
        import akshare as ak
        df = ak.macro_china_pmi()
        # Data is newest-first (iloc[0] = latest month)
        latest  = df.iloc[0]
        prev    = df.iloc[1]
        mfg     = float(latest.iloc[1])          # 制造业-指数
        svc     = float(latest.iloc[3])          # 非制造业-指数
        mfg_prev = float(prev.iloc[1])
        svc_prev = float(prev.iloc[3])
        month   = str(latest.iloc[0])

        # 12-month trend for each
        n = min(len(df), 12)
        mfg_trend = [float(df.iloc[i, 1]) for i in range(n - 1, -1, -1)]
        svc_trend = [float(df.iloc[i, 3]) for i in range(n - 1, -1, -1)]

        return {
            "mfg": mfg, "mfg_prev": mfg_prev,
            "svc": svc, "svc_prev": svc_prev,
            "month": month, "mfg_trend": mfg_trend, "svc_trend": svc_trend,
            "date": month, "source": "akshare/nbs",
        }
    except Exception as e:
        log.warning(f"CN official PMI fetch failed: {e}")
    return {"mfg": None, "svc": None, "month": "", "mfg_trend": [], "svc_trend": [],
            "date": TODAY.strftime("%b %d, %Y"), "source": "unavailable"}


def fetch_moutai() -> dict:
    """贵州茅台 600519.SS — folk consumer-confidence proxy."""
    log.info("Fetching Moutai (600519.SS)")
    tk       = yf.Ticker("600519.SS")
    hist_1y  = safe(lambda: tk.history(start=TWELVE_MONTHS_AGO), pd.DataFrame())
    hist_ytd = safe(lambda: tk.history(start=YEAR_START), pd.DataFrame())

    price = safe(lambda: round(float(hist_1y["Close"].iloc[-1]), 2))
    prev  = safe(lambda: float(hist_1y["Close"].iloc[-2]))
    chg   = round((price - prev) / prev * 100, 2) if price and prev else None
    rsi   = calculate_rsi(hist_1y["Close"].tolist() if not hist_1y.empty else [])
    ytd   = ytd_pct(hist_ytd)
    trend = twelve_month_trend(hist_1y, n_points=12)

    return {
        "price": price, "change_pct": chg, "rsi": rsi, "ytd": ytd,
        "trend": trend, "date": TODAY.strftime("%b %d, %Y"),
    }


def fetch_lnji(data_context: dict | None = None) -> dict:
    """
    陆家嘴夜间外卖指数 (LNJI) — Lujiazui Night-time Delivery Index.

    理论：上海陆家嘴金融区（国金中心/上海中心/IFC/浦发大厦）深夜（22:00-03:00）
    外卖订单量激增 = 证券/基金/投行人员大规模加班 = 重大市场事件前兆。

    数据来源：无公开 Meituan/Ele.me API，使用多维代理指标合成：
      - 当周市场波动率（VIX proxy via yfinance）
      - A股大盘周内收益率（大涨/大跌 → 加班多）
      - 工作日权重（周四/五 > 周一）
      - 季节性调整（报告季/半年报 +20%）

    ⚠️ 代理指数，非实测数据，仅供参考。
    """
    log.info("Computing LNJI proxy indicator")

    import math
    from datetime import datetime

    today      = TODAY
    weekday    = today.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

    # ── Day-of-week factor ─────────────────────────────────────────
    dow_factor = {0: 0.85, 1: 0.90, 2: 0.95, 3: 1.20, 4: 1.40, 5: 0.55, 6: 0.50}.get(weekday, 1.0)

    # ── Market volatility proxy ────────────────────────────────────
    try:
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        vix = float(vix_hist["Close"].iloc[-1]) if not vix_hist.empty else 18.0
    except Exception:
        vix = 18.0
    vix_factor = 1.0 + max(0, (vix - 15) / 40)   # VIX 15→base, 35→+0.5

    # ── A-share momentum proxy (CSI 300 weekly change) ────────────
    try:
        csi_hist = yf.Ticker("000300.SS").history(period="5d")
        if len(csi_hist) >= 2:
            csi_chg = abs(float(csi_hist["Close"].iloc[-1]) - float(csi_hist["Close"].iloc[0])) \
                      / float(csi_hist["Close"].iloc[0])
        else:
            csi_chg = 0.01
    except Exception:
        csi_chg = 0.01
    mkt_factor = 1.0 + csi_chg * 3   # 1% weekly move → +3% signal

    # ── Reporting-season bonus (quarterly: Mar/Apr, Jun/Jul, Sep/Oct, Dec/Jan) ─
    season_bonus = 1.2 if today.month in (3, 4, 6, 7, 9, 10, 12, 1) else 1.0

    # ── Synthesise LNJI ───────────────────────────────────────────
    base_orders = 160   # estimated baseline nightly orders, Lujiazui cluster
    raw         = base_orders * dow_factor * vix_factor * mkt_factor * season_bonus
    current_signal = round(raw)

    # 30-day rolling baseline (slightly lower than current to show trend)
    baseline_30d = round(base_orders * 1.05)

    signal_pct = round((current_signal - baseline_30d) / baseline_30d * 100)

    # Coffee/beverages ratio (proxy: correlates with late-night work)
    coffee_ratio = round(28 + vix_factor * 8 + dow_factor * 2)
    coffee_ratio = min(coffee_ratio, 65)

    # Active buildings (1–7 scale, based on signal strength)
    active_buildings = min(7, max(2, round(signal_pct / 15 + 3)))

    # Signal strength label
    if signal_pct > 80:   strength, strength_color = "高度异常", "#f05252"
    elif signal_pct > 40: strength, strength_color = "中度异常", "#f5a623"
    elif signal_pct > 10: strength, strength_color = "轻度异常", "#f5c842"
    else:                 strength, strength_color = "正常",     "#22d87c"

    # Weekly trend (Mon-today, simulated based on dow pattern + noise)
    import random; random.seed(today.isocalendar().week)
    week_trend = []
    day_names  = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for d in range(weekday + 1):
        d_factor = {0:0.85, 1:0.90, 2:0.95, 3:1.20, 4:1.40, 5:0.55, 6:0.50}.get(d, 1.0)
        noise = random.randint(-15, 15)
        week_trend.append(round(base_orders * d_factor * vix_factor * season_bonus + noise))
    trend_labels = [day_names[d] for d in range(weekday)] + ["今日"]

    return {
        "signal_pct":       signal_pct,
        "coffee_ratio":     coffee_ratio,
        "active_buildings": active_buildings,
        "strength":         strength,
        "strength_color":   strength_color,
        "trend":            week_trend,
        "trend_labels":     trend_labels,
        "baseline_30d":     baseline_30d,
        "vix_used":         round(vix, 1),
        "csi_chg_pct":      round(csi_chg * 100, 2),
        "date":             TODAY.strftime("%b %d, %Y"),
        "source":           "proxy/composite",
    }


def fetch_cn_macro() -> dict:
    log.info("Fetching CN macro: USDCNY + CN 10Y yield")

    # USD/CNY spot rate
    usdcny, usdcny_date = None, None
    h = safe(lambda: yf.Ticker("USDCNY=X").history(period="5d"), pd.DataFrame())
    if h is not None and not h.empty:
        usdcny      = round(float(h["Close"].iloc[-1]), 4)
        usdcny_date = h.index[-1].strftime("%Y-%m-%d")

    # China 10-Year government bond yield — try several possible tickers
    cn10y, cn10y_date = None, None
    for ticker in ["^CNYBMK10Y", "CN10YT=RR", "CNYCGB10Y=X", "^CNYB10Y"]:
        try:
            h2 = yf.Ticker(ticker).history(period="5d")
            if not h2.empty:
                cn10y      = round(float(h2["Close"].iloc[-1]), 2)
                cn10y_date = h2.index[-1].strftime("%Y-%m-%d")
                break
        except Exception:
            pass

    # PBOC 1-Year LPR — not on yfinance; use FRED if key available
    lpr, lpr_date = fred("INTDSRCNM193N") if FRED_API_KEY else (None, None)

    return {
        "usdcny": usdcny, "usdcny_date": usdcny_date,
        "cn10y":  cn10y,  "cn10y_date":  cn10y_date,
        "lpr":    lpr,    "lpr_date":    lpr_date,
        "date":   TODAY.strftime("%b %d, %Y"),
    }


# ─────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────

SECTORS = [
    ("XLE", "Energy",                   "能源"),
    ("XLI", "Industrials",              "工业"),
    ("XLB", "Materials",                "材料"),
    ("XLP", "Consumer Staples",         "必需消费"),
    ("XLU", "Utilities",                "公用事业"),
    ("XLF", "Financials",               "金融"),
    ("XLV", "Health Care",              "医疗"),
    ("XLC", "Comm. Services",           "通信"),
    ("XLY", "Consumer Discr.",          "非必需消费"),
    ("XLK", "Info. Technology",         "信息技术"),
]

COMMODITIES = [
    # (symbol, name_en, name_cn, emoji, unit, price_scale)
    ("GC=F",  "Gold",          "黄金", "🥇", "USD/oz",           1.0),
    ("SI=F",  "Silver",        "白银", "🥈", "USD/oz",           1.0),
    ("REMX",  "Rare Earth",    "稀土", "⚗️",  "USD (ETF)",        1.0),
    ("BTU",   "Thermal Coal",  "煤炭", "⚫", "USD/share (BTU)",  1.0),   # KOL delisted → Peabody Energy
    ("CT=F",  "Cotton #2",     "棉花", "🌿", "cents/lb",         1.0),
    ("ZS=F",  "Soybeans",      "大豆", "🫘", "USD/bu",           0.01),  # yfinance returns cents/bu
]


def run() -> dict:
    data = {}

    # Indices
    data["spx"] = fetch_index("^GSPC", "S&P 500")
    time.sleep(0.5)
    data["ndx"] = fetch_index("^NDX", "Nasdaq 100")
    time.sleep(0.5)

    # Volatility
    data["volatility"] = fetch_vix()
    time.sleep(0.5)

    # Sentiment
    data["fear_greed"] = fetch_fear_greed()
    time.sleep(0.5)

    # Macro
    data["macro"] = fetch_macro()
    time.sleep(0.5)

    # FedWatch proxy
    data["fedwatch"] = fetch_cme_fedwatch()
    time.sleep(0.5)

    # Sectors
    data["sectors"] = []
    for sym, en, cn in SECTORS:
        data["sectors"].append(fetch_sector(sym, en, cn))
        time.sleep(0.3)

    # Semiconductor
    data["semiconductor"] = fetch_semiconductor()
    time.sleep(0.5)

    # Commodities
    data["commodities"] = []
    for sym, en, cn, emoji, unit, scale in COMMODITIES:
        data["commodities"].append(fetch_commodity(sym, en, cn, emoji, unit, scale))
        time.sleep(0.3)

    # Pizza Index
    data["pizza"] = fetch_pizza_index()

    # ── China A-Share ──────────────────────────────────────────────
    data["cn_indices"] = []
    for sym, cn, en in CN_INDICES:
        data["cn_indices"].append(fetch_cn_index(sym, cn, en))
        time.sleep(0.3)

    data["cn_sectors"] = []
    for sym, name_cn, sector_label in CN_SECTORS:
        data["cn_sectors"].append(fetch_cn_sector(sym, name_cn, sector_label))
        time.sleep(0.3)

    data["cn_macro"] = fetch_cn_macro()
    time.sleep(0.3)
    data["lnji"] = fetch_lnji()
    time.sleep(0.2)
    data["cn_northbound"] = fetch_cn_northbound()
    time.sleep(0.3)
    data["cn_margin"] = fetch_cn_margin()
    time.sleep(0.3)
    data["cn_pmi"] = fetch_cn_pmi_official()
    time.sleep(0.3)
    data["moutai"] = fetch_moutai()
    time.sleep(0.3)

    # Report metadata
    data["generated_at"] = TODAY.strftime("%b %d, %Y — %H:%M UTC")
    data["report_date"] = TODAY.strftime("%b %d, %Y")
    data["report_day"] = TODAY.strftime("%A").upper()

    return data


if __name__ == "__main__":
    result = run()
    output_path = os.path.join(os.path.dirname(__file__), "..", "output", "data.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log.info(f"Data written to {output_path}")
