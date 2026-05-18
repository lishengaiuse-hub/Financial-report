"""
generate_report.py
Reads output/data.json and renders the full HTML market report.
"""

import os
import json
import math
from datetime import datetime

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def fmt(val, decimals=2, prefix="", suffix="", fallback="N/A"):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return fallback
    try:
        return f"{prefix}{float(val):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return fallback

def pct_color(val):
    if val is None: return "nt"
    return "up" if val >= 0 else "dn"

def rsi_color(val):
    if val is None: return "nt"
    if val >= 70: return "dn"
    if val >= 60: return "wn"
    if val <= 30: return "in"
    if val <= 40: return "in"
    return "nt"

def rsi_badge(val):
    if val is None: return '<span class="badge b-neutral">N/A</span>'
    if val >= 70: return '<span class="badge b-dn">Overbought</span>'
    if val >= 60: return '<span class="badge b-warn">High</span>'
    if val <= 30: return '<span class="badge b-info">Oversold</span>'
    if val <= 40: return '<span class="badge b-info">Low</span>'
    return '<span class="badge b-neutral">Neutral</span>'

def momentum_badge(m):
    colors = {
        "Leading":   ("b-up",   "Leading"),
        "Improving": ("b-info", "Improving"),
        "Weakening": ("b-warn", "Weakening"),
        "Lagging":   ("b-dn",   "Lagging"),
        "Neutral":   ("b-neutral","Neutral"),
    }
    c, t = colors.get(m, ("b-neutral", m))
    return f'<span class="pill {c}">{t}</span>'

def rsi_verdict(val):
    if val is None: return "数据不足"
    if val >= 70: return "⚠️ 超买，注意回调"
    if val >= 60: return "RSI偏高，谨慎追涨"
    if val <= 30: return "🔵 超卖，可寻机会"
    if val <= 40: return "RSI偏低，趋向超卖"
    return "中性区间"

def pin_pct(val, lo=0, hi=100):
    """Convert a value to a left:XX% string within [lo, hi]."""
    if val is None: return "50%"
    p = max(0.0, min(100.0, (float(val) - lo) / (hi - lo) * 100))
    return f"{p:.1f}%"

def sparkline_js(canvas_id, data, color, fill_color):
    if not data:
        return ""
    return f"""
    sparkline('{canvas_id}', {json.dumps(data)}, '{color}', '{fill_color}');"""

def sector_bar_html(ytd):
    if ytd is None: return ""
    w = min(abs(ytd) / 25 * 100, 100)
    color = "#22d87c" if ytd >= 0 else "#f05252"
    direction = "" if ytd >= 0 else "right:0;left:auto;"
    return f'<div class="bar-bg"><div class="bar-fill" style="width:{w:.0f}%;background:{color};{direction}"></div></div>'

def rsi_gauge_html(rsi_val):
    """Render a fixed RSI gauge with the pin correctly inside the bar wrapper."""
    left = pin_pct(rsi_val, 0, 100)
    val_str = fmt(rsi_val, 1, fallback="N/A")
    color = {"dn": "#f05252", "wn": "#f5a623", "in": "#4e9eff", "nt": "#8b909e"}.get(rsi_color(rsi_val), "#8b909e")
    return f"""
    <div class="rsi-gauge">
      <span class="rsi-lbl">RSI</span>
      <div class="rsi-body">
        <div class="rsi-bar">
          <div class="gs" style="width:30%;background:#f05252"></div>
          <div class="gs" style="width:40%;background:#2a3040"></div>
          <div class="gs" style="width:30%;background:#22d87c"></div>
        </div>
        <div class="rsi-pin-wrap">
          <div class="rsi-pin" style="left:{left}"></div>
        </div>
        <div class="rsi-ends"><span>0</span><span>30</span><span>70</span><span>100</span></div>
      </div>
      <span class="rsi-val" style="color:{color}">{val_str}</span>
    </div>"""

def gauge_html(val, lo, hi, segments, label, date_str, badge_html, color_class, val_fmt):
    left = pin_pct(val, lo, hi)
    segs_html = "".join(f'<div class="gs" style="width:{s[0]}%;background:{s[1]}"></div>' for s in segments)
    labels_html = "".join(f"<span>{l}</span>" for l in label.split("|"))
    return f"""
    <div class="card card-sm gauge">
      <p class="gauge-name">{val_fmt} {badge_html}</p>
      <p class="gauge-val {color_class}">{fmt(val, **{"prefix":"","suffix":"","decimals":2}) if val else "N/A"}</p>
      <p class="gauge-date">{date_str}</p>
      <div class="gbar">{segs_html}</div>
      <div class="mwrap"><div class="mkr" style="left:{left}"></div></div>
      <div class="glbls">{labels_html}</div>
    </div>"""


# ─────────────────────────────────────────────
# SECTION RENDERERS
# ─────────────────────────────────────────────

def render_pizza(p: dict) -> str:
    lvl = p.get("level", 5)
    status = p.get("status", "正常")
    date = p.get("date", "")
    segs = []
    labels = ["1 最高", "2 极端", "3 显著", "4 轻微", "5 正常"]
    colors = ["#501313","#A32D2D","#BA7517","rgba(34,216,124,0.2)","rgba(255,255,255,0.05)"]
    txt_colors = ["#F7C1C1","#FCEBEB","#FAC775","#22d87c","#8b909e"]
    for i, (lbl, bg, tc) in enumerate(zip(labels, colors, txt_colors), start=1):
        active = ' style="outline:2px solid rgba(255,255,255,0.6);outline-offset:2px"' if i == lvl else ""
        segs.append(f'<div class="dc-seg" style="background:{bg}"{active}>'
                    f'<p class="dc-seg-num" style="color:{tc}">{i}{"▲" if i==lvl else ""}</p>'
                    f'<p class="dc-seg-txt" style="color:{tc}">{lbl.split()[1]}</p></div>')

    badge_color = ["b-dn","b-dn","b-warn","b-up","b-neutral"][lvl-1]
    badge_label = ["最高警戒","极端飙升","显著上升","轻微异常","正常"][lvl-1]

    return f"""
<div class="card fade-in">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:12px">
    <div>
      <p style="font-size:15px;font-weight:600;margin-bottom:3px">
        Pentagon Pizza Index <span class="badge {badge_color}">{badge_label}</span>
      </p>
      <p style="font-size:11px;color:var(--text2)">追踪五角大楼周边披萨店 Google Maps 实时客流 vs. 历史基线</p>
      <p style="font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);margin-top:3px">
        {date} · pizzint.watch / @pizzintwatch
      </p>
    </div>
    <div style="text-align:center;flex-shrink:0">
      <div style="font-family:'DM Serif Display',serif;font-size:52px;line-height:1;color:{"#f05252" if lvl<=2 else "#f5a623" if lvl==3 else "#22d87c"}">{lvl}</div>
      <div style="font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;color:{"#f05252" if lvl<=2 else "#f5a623" if lvl==3 else "#22d87c"}">DOUGHCON</div>
    </div>
  </div>
  <div class="doughcon-row">{"".join(segs)}</div>
  <div class="grid-2" style="margin-top:10px">
    <div>
      <p style="font-size:11px;font-weight:500;margin-bottom:8px">五角大楼周边监测点状态</p>
      <div class="loc-grid">
        <div class="loc-card"><p class="loc-name">Extreme Pizza</p><p class="loc-dist">0.5mi · 最近</p>
          <p class="loc-pct">{"~100%" if lvl>=4 else "🚨 异常飙升"}</p>
          <div class="loc-bar"><div class="loc-bar-fill" style="width:{"40" if lvl>=4 else "90"}%"></div></div></div>
        <div class="loc-card"><p class="loc-name">District Pizza Palace</p><p class="loc-dist">1.0mi</p>
          <p class="loc-pct">{"~100%" if lvl>=4 else "🚨 异常"}</p>
          <div class="loc-bar"><div class="loc-bar-fill" style="width:{"40" if lvl>=4 else "80"}%"></div></div></div>
        <div class="loc-card"><p class="loc-name">Domino's Pizza</p><p class="loc-dist">1.4mi</p>
          <p class="loc-pct">{"~100%" if lvl>=4 else "🚨 异常"}</p>
          <div class="loc-bar"><div class="loc-bar-fill"></div></div></div>
        <div class="loc-card"><p class="loc-name">Pizzato Pizza</p><p class="loc-dist">2.2mi</p>
          <p class="loc-pct">{"~100%" if lvl>=4 else "🚨 异常"}</p>
          <div class="loc-bar"><div class="loc-bar-fill"></div></div></div>
      </div>
    </div>
    <div>
      <p style="font-size:11px;font-weight:500;margin-bottom:8px">历史关键信号</p>
      <div class="tl-item"><span class="tl-date">Feb 22, 2026</span><div class="tl-dot" style="background:#f05252"></div>
        <span class="tl-desc">DOUGHCON 1 → 6天后美伊战争爆发</span><span class="tl-val dn">+2,000%</span></div>
      <div class="tl-item"><span class="tl-date">Jun 2025</span><div class="tl-dot" style="background:#f05252"></div>
        <span class="tl-desc">4店飙升 → 以色列对伊朗重大打击</span><span class="tl-val dn">+200–400%</span></div>
      <div class="tl-item"><span class="tl-date">Jan 2, 2026</span><div class="tl-dot" style="background:#f5a623"></div>
        <span class="tl-desc">DOUGHCON 4 → 次日对委内瑞拉打击</span><span class="tl-val wn">轻微</span></div>
      <div class="tl-item"><span class="tl-date">Aug 1, 1990</span><div class="tl-dot" style="background:#555"></div>
        <span class="tl-desc">CIA单夜21个披萨 → 伊拉克入侵科威特</span><span class="tl-val nt">起源</span></div>
      <div style="background:rgba(34,216,124,0.07);border:1px solid rgba(34,216,124,0.15);border-radius:8px;padding:10px 12px;margin-top:8px">
        <p style="font-size:11px;font-weight:500;color:var(--up);margin-bottom:3px">DOUGHCON {lvl} — 当前解读</p>
        <p style="font-size:10px;color:var(--text2)">{status}. {"活动正常，短期升级风险相对可控。" if lvl>=4 else "活动异常，需密切关注地缘政治动态。"}</p>
      </div>
      <p style="font-size:9px;color:var(--text3);margin-top:8px">⚠️ 非官方OSINT指标，相关性≠因果性，不构成任何决策依据。</p>
    </div>
  </div>
</div>"""


def render_indices(spx: dict, ndx: dict) -> str:
    def idx_card(d, color, canvas):
        price = fmt(d.get("price"), 2)
        chg = d.get("change_pct")
        chg_str = f"{'▲' if chg and chg>=0 else '▽'} {fmt(abs(chg) if chg else 0, 2)}%" if chg is not None else "N/A"
        chg_col = "up" if chg and chg >= 0 else "dn"
        pe = fmt(d.get("pe"), 2, fallback="N/A")
        rsi = d.get("rsi")
        return f"""
    <div class="card" style="padding-bottom:0">
      <p class="card-name" style="color:{color};font-size:16px">{d["label"]}</p>
      <p style="font-family:'DM Serif Display',serif;font-size:30px;margin:4px 0 2px">
        {price} <span style="font-size:16px;color:var(--{chg_col})">{chg_str}</span>
      </p>
      <p class="card-sub">P/E: <strong>{pe}</strong> <span class="badge b-warn">High Valuation</span></p>
      <p class="card-sub" style="margin-top:3px">
        RSI(14): <strong class="{rsi_color(rsi)}">{fmt(rsi,2,fallback="N/A")}</strong> {rsi_badge(rsi)}
      </p>
      <div class="sparkline-area"><canvas id="{canvas}"></canvas></div>
      <p class="sparkline-lbl">10-Year Trend (illustrative)</p>
    </div>"""

    return f"""
<div class="grid-2 fade-in">
  {idx_card(spx, "#22d87c", "spxChart")}
  {idx_card(ndx, "#4e9eff", "ndxChart")}
</div>"""


def render_sentiment(vol: dict, fg: dict, spx: dict, ndx: dict) -> str:
    vix = vol.get("vix")
    vxn = vol.get("vxn")
    fg_val = fg.get("value")
    spx_rsi = spx.get("rsi")
    ndx_rsi = ndx.get("rsi")

    def vix_badge(v):
        if v is None: return '<span class="badge b-neutral">N/A</span>'
        if v > 30: return '<span class="badge b-dn">High Panic</span>'
        if v > 20: return '<span class="badge b-warn">Rising Fear</span>'
        if v < 12: return '<span class="badge b-up">Euphoria</span>'
        return '<span class="badge b-neutral">Normal</span>'

    def fg_badge(v):
        if v is None: return '<span class="badge b-neutral">N/A</span>'
        if v > 75: return '<span class="badge b-dn">Extreme Greed</span>'
        if v > 55: return '<span class="badge b-up">Greed</span>'
        if v > 44: return '<span class="badge b-neutral">Neutral</span>'
        if v > 24: return '<span class="badge b-warn">Fear</span>'
        return '<span class="badge b-info">Extreme Fear</span>'

    vix_left = pin_pct(vix, 0, 40)
    vxn_left = pin_pct(vxn, 0, 40)
    fg_left = pin_pct(fg_val, 0, 100)
    spx_rsi_left = pin_pct(spx_rsi, 0, 100)
    ndx_rsi_left = pin_pct(ndx_rsi, 0, 100)

    return f"""
<div class="grid-2 fade-in" style="gap:10px">
  <div class="card card-sm gauge">
    <p class="gauge-name">S&amp;P 500 RSI(14) {rsi_badge(spx_rsi)}</p>
    <p class="gauge-val {rsi_color(spx_rsi)}">{fmt(spx_rsi,2,fallback="N/A")}</p>
    <p class="gauge-date">{vol.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:30%;background:#f05252"></div>
      <div class="gs" style="width:40%;background:#2a3040"></div>
      <div class="gs" style="width:30%;background:#22d87c"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{spx_rsi_left}"></div></div>
    <div class="glbls"><span>Oversold &lt;30</span><span>Neutral 30–70</span><span>Overbought &gt;70</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">Nasdaq 100 RSI(14) {rsi_badge(ndx_rsi)}</p>
    <p class="gauge-val {rsi_color(ndx_rsi)}">{fmt(ndx_rsi,2,fallback="N/A")}</p>
    <p class="gauge-date">{vol.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:30%;background:#f05252"></div>
      <div class="gs" style="width:40%;background:#2a3040"></div>
      <div class="gs" style="width:30%;background:#22d87c"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{ndx_rsi_left}"></div></div>
    <div class="glbls"><span>Oversold &lt;30</span><span>Neutral 30–70</span><span>Overbought &gt;70</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">VIX Volatility Index {vix_badge(vix)}</p>
    <p class="gauge-val {"dn" if vix and vix>20 else "wn" if vix and vix>12 else "nt"}">{fmt(vix,2,fallback="N/A")}</p>
    <p class="gauge-date">{vol.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:25%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f07050"></div>
      <div class="gs" style="width:25%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{vix_left}"></div></div>
    <div class="glbls"><span>Euphoria &lt;12</span><span>Normal 12–20</span><span>Fear 20–30</span><span>Panic &gt;30</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">VXN Nasdaq Volatility {vix_badge(vxn)}</p>
    <p class="gauge-val {"dn" if vxn and vxn>20 else "wn" if vxn and vxn>12 else "nt"}">{fmt(vxn,2,fallback="N/A")}</p>
    <p class="gauge-date">{vol.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:25%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f07050"></div>
      <div class="gs" style="width:25%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{vxn_left}"></div></div>
    <div class="glbls"><span>Euphoria &lt;12</span><span>Normal 12–20</span><span>Fear 20–30</span><span>Panic &gt;30</span></div>
  </div>
</div>
<div class="card card-sm gauge fade-in" style="margin-top:10px">
  <p class="gauge-name">CNN Fear &amp; Greed Index {fg_badge(fg_val)}</p>
  <p class="gauge-val {"up" if fg_val and fg_val>55 else "dn" if fg_val and fg_val<25 else "wn" if fg_val and fg_val<45 else "nt"}">{fg_val if fg_val is not None else "N/A"}</p>
  <p class="gauge-date">{fg.get("date","")}</p>
  <div class="gbar">
    <div class="gs" style="width:25%;background:#f05252"></div>
    <div class="gs" style="width:20%;background:#f5a623"></div>
    <div class="gs" style="width:11%;background:#556"></div>
    <div class="gs" style="width:20%;background:#7aca56"></div>
    <div class="gs" style="width:24%;background:#22d87c"></div>
  </div>
  <div class="mwrap"><div class="mkr" style="left:{fg_left}"></div></div>
  <div class="glbls"><span>Extreme Fear 0–24</span><span>Fear 25–44</span><span>Neutral 45–55</span><span>Greed 56–75</span><span>Extreme Greed &gt;75</span></div>
</div>"""


def render_macro(m: dict, fw: dict) -> str:
    fed = m.get("fed_rate")
    t10y = m.get("t10y")
    dxy = m.get("dxy")
    cpi = m.get("cpi_yoy")
    core = m.get("core_cpi_yoy")
    nfp = m.get("nfp_change")
    icsa = m.get("icsa")
    ism_mfg = m.get("ism_mfg")
    ism_svc = m.get("ism_svc")
    unrate = m.get("unrate")

    fed_left = pin_pct(fed, 0, 6)
    t10y_left = pin_pct(t10y, 0, 6)
    dxy_left = pin_pct(dxy, 80, 120) if dxy else "50%"
    cpi_left = pin_pct(cpi, 0, 6)
    core_left = pin_pct(core, 0, 6)
    nfp_left = pin_pct(nfp, -100, 400) if nfp else "50%"
    ism_mfg_left = pin_pct(ism_mfg, 40, 60) if ism_mfg else "50%"
    ism_svc_left = pin_pct(ism_svc, 40, 60) if ism_svc else "50%"

    def pmi_badge(v):
        if v is None: return '<span class="badge b-neutral">N/A</span>'
        if v > 55: return '<span class="badge b-up">Strong</span>'
        if v > 50: return '<span class="badge b-up">Expanding</span>'
        if v > 48: return '<span class="badge b-warn">Contracting</span>'
        return '<span class="badge b-dn">Contraction</span>'

    return f"""
<div class="sec"><span class="sec-num">④</span><span class="sec-title">Monetary Policy</span><div class="sec-line"></div></div>
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">Fed Funds Rate <span class="badge b-neutral">{'On Hold' if fed else 'N/A'}</span></p>
    <p class="gauge-val nt">{fmt(fed,2,suffix="%",fallback="N/A")}</p>
    <p class="gauge-date">{m.get("fed_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:17%;background:#22d87c"></div>
      <div class="gs" style="width:33%;background:#4e9eff"></div>
      <div class="gs" style="width:33%;background:#f5a623"></div>
      <div class="gs" style="width:17%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{fed_left}"></div></div>
    <div class="glbls"><span>0–1% 宽松</span><span>1–3% 中性</span><span>3–5% 紧缩</span><span>&gt;5%</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">CME FedWatch — Implied Rate <span class="badge b-neutral">Futures</span></p>
    <p class="gauge-val nt">{fmt(fw.get("implied_rate"),3,suffix="%",fallback="N/A")}</p>
    <p class="gauge-date">{fw.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:100%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{pin_pct(fw.get("implied_rate"),0,6)}"></div></div>
    <div class="glbls"><span>0% 无降息</span><span>1次降息</span><span>2次+</span></div>
  </div>
</div>

<div class="sec"><span class="sec-num">⑤</span><span class="sec-title">Fixed Income &amp; Currency</span><div class="sec-line"></div></div>
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">10-Year Treasury Yield {"<span class='badge b-dn'>High</span>" if t10y and t10y>4 else "<span class='badge b-neutral'>Normal</span>"}</p>
    <p class="gauge-val {"dn" if t10y and t10y>4 else "wn" if t10y and t10y>3 else "up"}">{fmt(t10y,2,suffix="%",fallback="N/A")}</p>
    <p class="gauge-date">{m.get("t10y_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:35%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f07050"></div>
      <div class="gs" style="width:15%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{t10y_left}"></div></div>
    <div class="glbls"><span>&lt;3% 低</span><span>3–4% 正常</span><span>4–5% 偏高</span><span>&gt;5%</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">DXY 美元指数 <span class="badge b-neutral">Trade-Weighted</span></p>
    <p class="gauge-val wn">{fmt(dxy,2,fallback="N/A")}</p>
    <p class="gauge-date">{m.get("dxy_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:35%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f07050"></div>
      <div class="gs" style="width:15%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{dxy_left}"></div></div>
    <div class="glbls"><span>弱 &lt;95</span><span>95–105</span><span>强 &gt;105</span><span>极强</span></div>
  </div>
</div>

<div class="sec"><span class="sec-num">⑥</span><span class="sec-title">Inflation</span><div class="sec-line"></div></div>
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">CPI Headline YoY {"<span class='badge b-dn'>High</span>" if cpi and cpi>3 else "<span class='badge b-warn'>Watch</span>" if cpi and cpi>2 else "<span class='badge b-up'>On Target</span>"}</p>
    <p class="gauge-val {"dn" if cpi and cpi>3 else "wn" if cpi and cpi>2 else "up"}">{fmt(cpi,1,suffix="%",fallback="N/A")}</p>
    <p class="gauge-date">{m.get("cpi_date","") or m.get("date","")} · Fed目标 2%</p>
    <div class="gbar">
      <div class="gs" style="width:20%;background:#22d87c"></div>
      <div class="gs" style="width:20%;background:#f5a623"></div>
      <div class="gs" style="width:30%;background:#f07050"></div>
      <div class="gs" style="width:30%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{cpi_left}"></div></div>
    <div class="glbls"><span>&lt;2% 达标</span><span>2–3%</span><span>3–4.5% 高</span><span>&gt;4.5%</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">Core CPI YoY {"<span class='badge b-dn'>Elevated</span>" if core and core>3 else "<span class='badge b-warn'>Watch</span>" if core and core>2 else "<span class='badge b-up'>Easing</span>"}</p>
    <p class="gauge-val {"dn" if core and core>3 else "wn" if core and core>2 else "up"}">{fmt(core,1,suffix="%",fallback="N/A")}</p>
    <p class="gauge-date">{m.get("core_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:20%;background:#22d87c"></div>
      <div class="gs" style="width:20%;background:#f5a623"></div>
      <div class="gs" style="width:30%;background:#f07050"></div>
      <div class="gs" style="width:30%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{core_left}"></div></div>
    <div class="glbls"><span>&lt;2%</span><span>2–3%</span><span>3–4.5%</span><span>&gt;4.5%</span></div>
  </div>
</div>

<div class="sec"><span class="sec-num">⑦</span><span class="sec-title">Employment</span><div class="sec-line"></div></div>
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">NFP 非农就业 {"<span class='badge b-up'>Strong</span>" if nfp and nfp>150 else "<span class='badge b-up'>Solid</span>" if nfp and nfp>75 else "<span class='badge b-warn'>Weak</span>" if nfp and nfp>0 else "<span class='badge b-dn'>Negative</span>"}</p>
    <p class="gauge-val {"up" if nfp and nfp>75 else "wn" if nfp and nfp>0 else "dn"}">{("+"+fmt(nfp,0,suffix="K")) if nfp and nfp>=0 else fmt(nfp,0,suffix="K") if nfp else "N/A"}</p>
    <p class="gauge-date">{m.get("nfp_date","") or m.get("date","")} · 失业率 {fmt(unrate,1,suffix="%",fallback="N/A")}</p>
    <div class="gbar">
      <div class="gs" style="width:20%;background:#f05252"></div>
      <div class="gs" style="width:30%;background:#f5a623"></div>
      <div class="gs" style="width:30%;background:#22d87c"></div>
      <div class="gs" style="width:20%;background:#4e9eff"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{nfp_left}"></div></div>
    <div class="glbls"><span>&lt;0 收缩</span><span>0–75K 弱</span><span>75–200K</span><span>&gt;200K 热</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">初请失业金 Weekly {"<span class='badge b-up'>Low</span>" if icsa and icsa<225 else "<span class='badge b-neutral'>Normal</span>" if icsa and icsa<300 else "<span class='badge b-warn'>Elevated</span>"}</p>
    <p class="gauge-val {"up" if icsa and icsa<225 else "wn" if icsa and icsa<300 else "dn"}">{fmt(icsa,0,suffix="K",fallback="N/A")}</p>
    <p class="gauge-date">{m.get("icsa_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:35%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f07050"></div>
      <div class="gs" style="width:15%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{pin_pct(icsa,100,500) if icsa else "40%"}"></div></div>
    <div class="glbls"><span>&lt;200K 强</span><span>200–250K</span><span>250–350K</span><span>&gt;350K</span></div>
  </div>
</div>

<div class="sec"><span class="sec-num">⑧</span><span class="sec-title">ISM PMI — Leading Indicators</span><div class="sec-line"></div></div>
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">ISM 制造业 PMI {pmi_badge(ism_mfg)}</p>
    <p class="gauge-val {"up" if ism_mfg and ism_mfg>50 else "dn"}">{fmt(ism_mfg,1,fallback="N/A")}</p>
    <p class="gauge-date">{m.get("ism_mfg_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:30%;background:#f05252"></div>
      <div class="gs" style="width:20%;background:#556"></div>
      <div class="gs" style="width:25%;background:#7aca56"></div>
      <div class="gs" style="width:25%;background:#22d87c"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{ism_mfg_left}"></div></div>
    <div class="glbls"><span>收缩&lt;50</span><span>~50荣枯线</span><span>50–55扩张</span><span>&gt;55强劲</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">ISM 服务业 PMI {pmi_badge(ism_svc)}</p>
    <p class="gauge-val {"up" if ism_svc and ism_svc>50 else "dn"}">{fmt(ism_svc,1,fallback="N/A")}</p>
    <p class="gauge-date">{m.get("ism_svc_date","") or m.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:30%;background:#f05252"></div>
      <div class="gs" style="width:20%;background:#556"></div>
      <div class="gs" style="width:25%;background:#7aca56"></div>
      <div class="gs" style="width:25%;background:#22d87c"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{ism_svc_left}"></div></div>
    <div class="glbls"><span>收缩&lt;50</span><span>~50荣枯线</span><span>50–55扩张</span><span>&gt;55强劲</span></div>
  </div>
</div>"""


def render_sectors(sectors: list) -> str:
    sorted_s = sorted(sectors, key=lambda x: x.get("ytd") or 0, reverse=True)
    labels = json.dumps([f"{s['symbol']} {s['name_cn']}" for s in sorted_s])
    ytd_vals = json.dumps([s.get("ytd") or 0 for s in sorted_s])
    colors = json.dumps(["#22d87c" if (s.get("ytd") or 0) >= 0 else "#f05252" for s in sorted_s])
    rsi_vals = json.dumps([s.get("rsi") or 50 for s in sorted_s])
    rsi_colors = json.dumps([
        "#f05252" if (s.get("rsi") or 50) >= 70 else
        "#f5a623" if (s.get("rsi") or 50) >= 60 else
        "#556677" if (s.get("rsi") or 50) >= 40 else
        "#4e9eff" for s in sorted_s
    ])

    rows = ""
    for s in sorted_s:
        ytd = s.get("ytd")
        rsi = s.get("rsi")
        price = s.get("price")
        rows += f"""
        <tr>
          <td><strong>{s["symbol"]}</strong></td>
          <td style="color:var(--text2)">{s["name_cn"]}</td>
          <td style="text-align:right;color:var(--{"up" if (ytd or 0)>=0 else "dn"});font-weight:600">
            {"$"+fmt(price,2,fallback="N/A")}</td>
          <td style="text-align:right;color:var(--{"up" if (ytd or 0)>=0 else "dn"});font-weight:600">
            {("+"+fmt(ytd,1,suffix="%")) if ytd and ytd>=0 else fmt(ytd,1,suffix="%") if ytd else "N/A"}</td>
          <td>{sector_bar_html(ytd)}</td>
          <td style="font-family:'DM Mono',monospace;color:{rsi_color(rsi)};font-weight:500">{fmt(rsi,1,fallback="N/A")}</td>
          <td>{momentum_badge(s.get("momentum","Neutral"))}</td>
          <td style="font-size:10px;color:var(--text2)">{rsi_verdict(rsi)}</td>
        </tr>"""

    return f"""
<div class="card fade-in" style="margin-bottom:12px">
  <div class="chart-wrap chart-wrap-md"><canvas id="sectorChart"></canvas></div>
</div>
<div class="card fade-in">
  <table class="sector-table">
    <thead>
      <tr>
        <th>ETF</th><th>板块</th><th style="text-align:right">价格</th>
        <th style="text-align:right">YTD</th><th>走势</th>
        <th>RSI(14)</th><th>动能</th><th>技术判断</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<script>
(function(){{
  const sLabels={labels};
  const sYtd={ytd_vals};
  const sColors={colors};
  new Chart(document.getElementById('sectorChart'),{{
    type:'bar',
    data:{{labels:sLabels,datasets:[{{label:'YTD %',data:sYtd,backgroundColor:sColors,borderRadius:5,borderSkipped:false}}]}},
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>' '+(c.raw>=0?'+':'')+c.raw.toFixed(1)+'%'}}}}}},
      scales:{{x:{{grid:{{color:'rgba(255,255,255,0.05)'}},ticks:{{callback:v=>(v>=0?'+':'')+v+'%'}}}},
               y:{{grid:{{display:false}},border:{{display:false}}}}}}
    }},
    plugins:[{{afterDraw(c){{
      const ctx=c.ctx,xs=c.scales.x,ys=c.scales.y;
      const x0=xs.getPixelForValue(0);
      ctx.save();ctx.beginPath();ctx.moveTo(x0,ys.top);ctx.lineTo(x0,ys.bottom);
      ctx.strokeStyle='rgba(255,255,255,0.25)';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.stroke();ctx.restore();
    }}}}]
  }});
  // RSI chart
  const rLabels={labels};
  const rVals={rsi_vals};
  const rColors={rsi_colors};
  new Chart(document.getElementById('rsiChart'),{{
    type:'bar',
    data:{{labels:rLabels,datasets:[{{label:'RSI(14)',data:rVals,backgroundColor:rColors,borderRadius:5,borderSkipped:false}}]}},
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>' RSI: '+c.raw.toFixed(1)}}}}}},
      scales:{{x:{{min:0,max:100,grid:{{color:'rgba(255,255,255,0.05)'}}}},y:{{grid:{{display:false}},border:{{display:false}}}}}}
    }},
    plugins:[{{afterDraw(c){{
      const ctx=c.ctx,xs=c.scales.x,ys=c.scales.y;
      [{{v:70,col:'rgba(240,82,82,0.7)',lbl:'超买 70'}},{{v:30,col:'rgba(78,158,255,0.7)',lbl:'超卖 30'}}].forEach(o=>{{
        const x=xs.getPixelForValue(o.v);
        ctx.save();ctx.beginPath();ctx.moveTo(x,ys.top);ctx.lineTo(x,ys.bottom);
        ctx.strokeStyle=o.col;ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.stroke();
        ctx.fillStyle=o.col;ctx.font='bold 9px monospace';ctx.fillText(o.lbl,x+3,ys.top+11);ctx.restore();
      }});
    }}}}]
  }});
}})();
</script>"""


def render_semiconductor(s: dict) -> str:
    soxx_price = fmt(s.get("soxx_price"), 2, prefix="$", fallback="N/A")
    soxx_rsi = s.get("soxx_rsi")
    soxx_ytd = s.get("soxx_ytd")
    sox_price = fmt(s.get("sox_price"), 0, fallback="N/A")
    sox_rsi = s.get("sox_rsi")

    return f"""
<div class="grid-2 fade-in">
  <div class="semi-card">
    <p style="font-size:14px;font-weight:600;color:var(--info);margin-bottom:3px">SOX · Philadelphia Semiconductor Index</p>
    <p style="font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);margin-bottom:8px">{s.get("date","")}</p>
    <p style="font-family:'DM Serif Display',serif;font-size:28px;margin-bottom:4px">{sox_price}</p>
    <p style="font-size:12px;color:var(--up);font-weight:500;margin-bottom:3px">RSI: {fmt(sox_rsi,1,fallback="N/A")} {rsi_badge(sox_rsi)}</p>
    {rsi_gauge_html(sox_rsi)}
    <div class="semi-spark"><canvas id="soxChart"></canvas></div>
    <p class="semi-spark-lbl">12-Month Trend (illustrative)</p>
  </div>
  <div class="semi-card">
    <p style="font-size:14px;font-weight:600;color:var(--info);margin-bottom:3px">SOXX · iShares PHLX Semiconductor ETF</p>
    <p style="font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);margin-bottom:8px">{s.get("date","")}</p>
    <p style="font-family:'DM Serif Display',serif;font-size:28px;margin-bottom:4px">{soxx_price}</p>
    <p style="font-size:12px;color:var(--{"up" if (soxx_ytd or 0)>=0 else "dn"});font-weight:500;margin-bottom:3px">
      YTD: {("+"+fmt(soxx_ytd,1,suffix="%")) if soxx_ytd and soxx_ytd>=0 else fmt(soxx_ytd,1,suffix="%") if soxx_ytd else "N/A"} &nbsp;·&nbsp;
      52W: ${fmt(s.get("soxx_52w_low"),2,fallback="N/A")} – ${fmt(s.get("soxx_52w_high"),2,fallback="N/A")}
    </p>
    {rsi_gauge_html(soxx_rsi)}
    <div class="semi-detail">
      <span style="color:var(--text)">核心驱动:</span> AI算力需求 · NVDA/AVGO/TSM主导 · 数据中心资本开支<br>
      <span style="color:var(--text)">主要风险:</span> {"RSI "+fmt(soxx_rsi,1)+"偏高，注意回调" if soxx_rsi and soxx_rsi>65 else "技术中性，关注成交量"} · 估值 · 地缘科技管制
    </div>
    <div class="semi-spark"><canvas id="soxxChart"></canvas></div>
    <p class="semi-spark-lbl">12-Month Trend (illustrative)</p>
  </div>
</div>"""


def render_commodities(comms: list) -> str:
    cards = ""
    for c in comms:
        rsi = c.get("rsi")
        ytd = c.get("ytd")
        price = c.get("price")
        left = pin_pct(rsi, 0, 100)
        rsi_c = rsi_color(rsi)
        rsi_col_hex = {"dn":"#f05252","wn":"#f5a623","in":"#4e9eff","nt":"#8b909e"}.get(rsi_c,"#8b909e")

        ytd_str = ("+"+fmt(ytd,1,suffix="%")) if ytd and ytd>=0 else fmt(ytd,1,suffix="%") if ytd else "N/A"
        ytd_badge = "b-up" if (ytd or 0)>=0 else "b-dn"
        price_col = "up" if (ytd or 0)>=0 else "dn" if (ytd or 0)<-5 else "nt"

        price_fmt = fmt(price,2,prefix="$",fallback="N/A")
        if c["unit"] == "cents/lb" and price:
            price_fmt = f"{fmt(price,2,fallback='N/A')}¢"

        canvas_id = f"com_{c['symbol'].replace('=','_').replace('^','')}"

        cards += f"""
  <div class="com-card">
    <p class="com-icon">{c["emoji"]}</p>
    <p class="com-name">{c["name_cn"]} {c["name_en"]}</p>
    <p class="com-unit">{c["symbol"]} · {c["unit"]}</p>
    <p class="com-price {price_col}">{price_fmt}</p>
    <p class="com-ytd {price_col}">YTD {ytd_str} <span class="badge {ytd_badge}">{"涨" if (ytd or 0)>=0 else "跌"}</span></p>
    <div class="rsi-gauge">
      <span class="rsi-lbl">RSI</span>
      <div class="rsi-body">
        <div class="rsi-bar">
          <div class="gs" style="width:30%;background:#f05252"></div>
          <div class="gs" style="width:40%;background:#2a3040"></div>
          <div class="gs" style="width:30%;background:#22d87c"></div>
        </div>
        <div class="rsi-pin-wrap"><div class="rsi-pin" style="left:{left}"></div></div>
        <div class="rsi-ends"><span>0</span><span>30</span><span>70</span><span>100</span></div>
      </div>
      <span class="rsi-val" style="color:{rsi_col_hex}">{fmt(rsi,1,fallback="N/A")}</span>
    </div>
    <p class="com-key">{rsi_verdict(rsi)} · 52周波动显著 · {c.get("date","")}</p>
    <div class="com-spark"><canvas id="{canvas_id}"></canvas></div>
    <p class="com-spark-lbl">12-Month Trend</p>
  </div>"""

    js = "".join(
        sparkline_js(
            f"com_{c['symbol'].replace('=','_').replace('^','')}",
            c.get("trend") or [],
            "#22d87c" if (c.get("ytd") or 0)>=0 else "#f05252",
            "rgba(34,216,124,0.12)" if (c.get("ytd") or 0)>=0 else "rgba(240,82,82,0.1)"
        )
        for c in comms
    )

    return f'<div class="grid-3 fade-in">{cards}</div><script>(function(){{{js}}})();</script>'


def render_watchlist(data: dict) -> str:
    sectors = data.get("sectors", [])
    spx_rsi = data.get("spx", {}).get("rsi")
    fg = data.get("fear_greed", {}).get("value")
    sox_rsi = data.get("semiconductor", {}).get("sox_rsi")
    pizza_lvl = data.get("pizza", {}).get("level", 5)
    cpi = data.get("macro", {}).get("cpi_yoy")
    t10y = data.get("macro", {}).get("t10y")
    date = data.get("report_date", "")

    signals = []

    # Pizza
    pizza_dot = "da2" if pizza_lvl <= 3 else "dg2" if pizza_lvl == 5 else "db2"
    signals.append((pizza_dot, f"PizzINT DOUGHCON {pizza_lvl}",
                    "五角大楼活动正常，短期升级风险可控" if pizza_lvl >= 4 else "⚠️ 异常活动！请密切关注地缘政治动态", date))

    if cpi and cpi > 3:
        signals.append(("dr2", f"CPI {fmt(cpi,1,suffix='%')} 高于目标",
                        "通胀顽固，Fed降息压力增大，高估值股受压", date))
    elif cpi and cpi > 2:
        signals.append(("da2", f"CPI {fmt(cpi,1,suffix='%')} 高于目标",
                        "通胀高于2%目标，Fed仍需谨慎", date))

    if t10y and t10y > 4:
        signals.append(("dr2", f"10Y国债收益率 {fmt(t10y,2,suffix='%')}",
                        "高利率持续压制成长股和高P/E板块估值", date))

    if spx_rsi and spx_rsi > 70:
        signals.append(("dr2", f"S&P 500 RSI {fmt(spx_rsi,1)} 超买",
                        "大盘技术超买，短期回调风险上升", date))
    if fg and fg > 70:
        signals.append(("da2", f"F&G Index {fg} 贪婪区",
                        "市场情绪偏热，结合技术超买需警惕", date))

    if sox_rsi and sox_rsi > 70:
        signals.append(("dr2", f"SOX 半导体 RSI {fmt(sox_rsi,1)} 超买",
                        "半导体板块技术极度拉伸，回调风险显著", date))

    # Find lagging/oversold sectors
    lagging = [s for s in sectors if s.get("rsi") and s["rsi"] < 42]
    if lagging:
        names = " · ".join(s["symbol"] for s in lagging)
        signals.append(("db2", f"{names} RSI趋向超卖",
                        "关注反弹机会，若RSI<35可布局", date))

    leading = [s for s in sectors if s.get("rsi") and s["rsi"] > 65]
    if leading:
        names = " · ".join(s["symbol"] for s in leading)
        signals.append(("da2", f"{names} RSI偏高 {fmt(leading[0].get('rsi'),1)}",
                        "领涨板块技术面偏热，谨慎追高", date))

    items = ""
    for dot, name, note, d in signals[:12]:
        items += f"""
    <div class="watch-item">
      <div class="watch-dot" style="background:var(--{"dn" if dot=="dr2" else "warn" if dot=="da2" else "info" if dot=="db2" else "up"})"></div>
      <p class="watch-name">{name}</p>
      <p class="watch-note">{note}</p>
      <span class="watch-date">{d}</span>
    </div>"""

    # Strategy recommendation
    strategy_lines = ["Continue regular investment · Cautious buying · Manage position size"]
    oversold_secs = [s["symbol"] for s in sectors if s.get("rsi") and s["rsi"] < 42]
    overbought_secs = [s["symbol"] for s in sectors if s.get("rsi") and s["rsi"] > 65]
    if overbought_secs:
        strategy_lines.append(f"规避超买板块: {', '.join(overbought_secs)}")
    if oversold_secs:
        strategy_lines.append(f"关注超卖反弹机会: {', '.join(oversold_secs)}")
    if spx_rsi and spx_rsi > 70:
        strategy_lines.append("大盘整体超买，建议控制仓位，等待回调再加仓")

    strategy_html = "<br>".join(strategy_lines)
    return f"""
<div class="card fade-in">{"".join([items])}</div>
<div style="margin-top:20px">
  <div class="strategy fade-in">
    <div class="strategy-icon">🎯</div>
    <div>
      <p class="strategy-title">Today's Strategy Recommendation</p>
      <p class="strategy-body">{strategy_html}</p>
    </div>
  </div>
</div>"""


# ─────────────────────────────────────────────
# AI ANALYSIS RENDERER
# ─────────────────────────────────────────────

def render_ai_analysis(ai: dict) -> str:
    commentary = ai.get("commentary")
    model      = ai.get("model", "deepseek-chat")
    tokens     = ai.get("tokens_used", 0)
    error      = ai.get("error")

    if not commentary:
        reason = {
            "no_api_key":           "未配置 DEEPSEEK_API_KEY，跳过 AI 解读。",
            "openai_not_installed": "openai 包未安装，跳过 AI 解读。",
        }.get(error, f"AI 解读生成失败（{error}）。")
        return f"""
<div class="card fade-in" style="border-color:rgba(200,169,110,0.15)">
  <p style="font-size:11px;color:var(--text3);text-align:center;padding:16px 0">{reason}</p>
</div>"""

    # Paragraph breaks: split on double-newline or numbered list markers
    paras = [p.strip() for p in commentary.replace("①","<br><br>①").replace("②","<br><br>②")
             .replace("③","<br><br>③").replace("④","<br><br>④").replace("⑤","<br><br>⑤")
             .split("<br><br>") if p.strip()]
    body_html = "</p><p style='margin-top:10px;font-size:13px;color:#c8c0a8;line-height:1.8'>".join(paras)

    return f"""
<div class="card fade-in" style="background:linear-gradient(135deg,rgba(200,169,110,0.06),rgba(200,169,110,0.02));
     border:1px solid rgba(200,169,110,0.2);">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:8px">
    <div style="display:flex;align-items:center;gap:10px">
      <span style="font-size:20px">🤖</span>
      <div>
        <p style="font-size:13px;font-weight:600;color:var(--accent)">AI 市场情报解读</p>
        <p style="font-size:9px;font-family:'DM Mono',monospace;color:var(--text3)">
          Powered by {model} &nbsp;·&nbsp; {tokens} tokens
        </p>
      </div>
    </div>
    <span class="badge b-accent">DeepSeek</span>
  </div>
  <p style="font-size:13px;color:#c8c0a8;line-height:1.8">{body_html}</p>
  <p style="font-size:9px;color:var(--text3);margin-top:12px;font-family:'DM Mono',monospace">
    ⚠️ AI 生成内容仅供参考，不构成投资建议。模型可能存在幻觉，请结合原始数据独立判断。
  </p>
</div>"""


# ─────────────────────────────────────────────
# CHINA A-SHARE RENDERERS
# ─────────────────────────────────────────────

# Colors for the 5 CN indices (kept consistent across all charts)
_CN_COLORS = ["#f5a623", "#4e9eff", "#22d87c", "#c8a96e", "#b06aff"]
_CN_FILLS  = ["rgba(245,166,35,0.12)", "rgba(78,158,255,0.12)",
              "rgba(34,216,124,0.12)", "rgba(200,169,110,0.12)",
              "rgba(176,106,255,0.12)"]


def render_cn_indices(cn_indices: list) -> str:
    def idx_card(d, color, canvas_id):
        price   = fmt(d.get("price"), 2)
        chg     = d.get("change_pct")
        chg_col = "up" if chg and chg >= 0 else "dn"
        sign    = "▲" if chg and chg >= 0 else "▽"
        chg_str = f"{sign} {fmt(abs(chg) if chg else 0, 2)}%" if chg is not None else "N/A"
        rsi     = d.get("rsi")
        ytd     = d.get("ytd")
        pe      = fmt(d.get("pe"), 2, fallback="")
        ytd_str = ("+"+fmt(ytd,1,suffix="%")) if ytd and ytd>=0 else fmt(ytd,1,suffix="%") if ytd else "N/A"
        pe_line = f"<p class='card-sub' style='margin-top:2px'>P/E: <strong>{pe}</strong></p>" if pe else ""
        return f"""
  <div class="card" style="padding-bottom:0">
    <p style="font-size:12px;font-weight:700;color:{color};margin-bottom:1px">{d['name_cn']}</p>
    <p style="font-size:9px;font-family:'DM Mono',monospace;color:var(--text3);margin-bottom:4px">{d['name_en']}</p>
    <p style="font-family:'DM Serif Display',serif;font-size:22px;margin:3px 0 2px">
      {price} <span style="font-size:13px;color:var(--{chg_col})">{chg_str}</span>
    </p>
    <p class="card-sub">YTD <strong class="{pct_color(ytd)}">{ytd_str}</strong></p>
    <p class="card-sub" style="margin-top:2px">RSI(14): <strong class="{rsi_color(rsi)}">{fmt(rsi,1,fallback="N/A")}</strong> {rsi_badge(rsi)}</p>
    {pe_line}
    <div class="sparkline-area"><canvas id="{canvas_id}"></canvas></div>
    <p class="sparkline-lbl">12-Month Trend</p>
  </div>"""

    cards = [idx_card(d, col, f"cn_{d['symbol'].replace('.','_')}")
             for d, col in zip(cn_indices, _CN_COLORS)]
    rows  = ""
    if len(cards) >= 3:
        rows += f'<div class="grid-3 fade-in">{"".join(cards[:3])}</div>'
    if len(cards) >= 5:
        rows += f'<div class="grid-2 fade-in" style="margin-top:12px">{"".join(cards[3:5])}</div>'

    js = ""
    for d, col, fill in zip(cn_indices, _CN_COLORS, _CN_FILLS):
        cid   = f"cn_{d['symbol'].replace('.','_')}"
        trend = d.get("trend_1y") or []
        js   += f"\nsparkline('{cid}',{json.dumps(trend)},'{col}','{fill}');"

    return f"{rows}<script>(function(){{{js}}})();</script>"


def render_cn_rsi(cn_indices: list) -> str:
    srt    = sorted(cn_indices, key=lambda x: x.get("rsi") or 50, reverse=True)
    labels = json.dumps([f"{d['symbol']} {d['name_cn']}" for d in srt])
    vals   = json.dumps([round(d.get("rsi") or 50, 1) for d in srt])
    colors = json.dumps([
        "#f05252" if (d.get("rsi") or 50) >= 70 else
        "#f5a623" if (d.get("rsi") or 50) >= 60 else
        "#556677" if (d.get("rsi") or 50) >= 40 else
        "#4e9eff" for d in srt
    ])
    return f"""
<div class="card fade-in"><div style="height:200px;position:relative"><canvas id="cnRsiChart"></canvas></div></div>
<script>(function(){{
  new Chart(document.getElementById('cnRsiChart'),{{
    type:'bar',
    data:{{labels:{labels},datasets:[{{label:'RSI(14)',data:{vals},backgroundColor:{colors},borderRadius:5,borderSkipped:false}}]}},
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>' RSI: '+c.raw.toFixed(1)}}}}}},
      scales:{{x:{{min:0,max:100,grid:{{color:'rgba(255,255,255,0.05)'}}}},
               y:{{grid:{{display:false}},border:{{display:false}}}}}}
    }},
    plugins:[{{afterDraw(c){{
      const ctx=c.ctx,xs=c.scales.x,ys=c.scales.y;
      [{{v:70,col:'rgba(240,82,82,0.7)',lbl:'超买 70'}},{{v:30,col:'rgba(78,158,255,0.7)',lbl:'超卖 30'}}].forEach(o=>{{
        const x=xs.getPixelForValue(o.v);
        ctx.save();ctx.beginPath();ctx.moveTo(x,ys.top);ctx.lineTo(x,ys.bottom);
        ctx.strokeStyle=o.col;ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.stroke();
        ctx.fillStyle=o.col;ctx.font='bold 9px monospace';ctx.fillText(o.lbl,x+3,ys.top+11);
        ctx.restore();
      }});
    }}}}]
  }});
}})();</script>"""


def render_cn_sectors(cn_sectors: list) -> str:
    srt    = sorted(cn_sectors, key=lambda x: x.get("ytd") or 0, reverse=True)
    labels = json.dumps([s["name_cn"] for s in srt])
    ytds   = json.dumps([round(s.get("ytd") or 0, 1) for s in srt])
    colors = json.dumps(["#22d87c" if (s.get("ytd") or 0) >= 0 else "#f05252" for s in srt])

    rows = ""
    for s in srt:
        ytd, rsi, price = s.get("ytd"), s.get("rsi"), s.get("price")
        ytd_str = ("+"+fmt(ytd,1,suffix="%")) if ytd and ytd>=0 else fmt(ytd,1,suffix="%") if ytd else "N/A"
        rows += f"""
        <tr>
          <td><strong style="font-family:'DM Mono',monospace;font-size:10px;color:var(--text2)">{s['symbol']}</strong></td>
          <td style="font-weight:500">{s['name_cn']}</td>
          <td style="color:var(--text2)">{s['sector_label']}</td>
          <td style="text-align:right;color:var(--{"up" if (ytd or 0)>=0 else "dn"});font-weight:600">
            ¥{fmt(price,3,fallback="N/A")}</td>
          <td style="text-align:right;color:var(--{"up" if (ytd or 0)>=0 else "dn"});font-weight:600">
            {ytd_str}</td>
          <td>{sector_bar_html(ytd)}</td>
          <td style="font-family:'DM Mono',monospace;color:{rsi_color(rsi)};font-weight:500">{fmt(rsi,1,fallback="N/A")}</td>
          <td>{momentum_badge(s.get("momentum","Neutral"))}</td>
        </tr>"""

    return f"""
<div class="card fade-in" style="margin-bottom:12px">
  <div style="height:240px;position:relative"><canvas id="cnSectorChart"></canvas></div>
</div>
<div class="card fade-in">
  <table class="sector-table">
    <thead><tr><th>代码</th><th>ETF</th><th>板块</th>
      <th style="text-align:right">价格(¥)</th><th style="text-align:right">YTD</th>
      <th>走势</th><th>RSI(14)</th><th>动能</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<script>(function(){{
  new Chart(document.getElementById('cnSectorChart'),{{
    type:'bar',
    data:{{labels:{labels},datasets:[{{label:'YTD %',data:{ytds},backgroundColor:{colors},borderRadius:5,borderSkipped:false}}]}},
    options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>' '+(c.raw>=0?'+':'')+c.raw.toFixed(1)+'%'}}}}}},
      scales:{{x:{{grid:{{color:'rgba(255,255,255,0.05)'}},ticks:{{callback:v=>(v>=0?'+':'')+v+'%'}}}},
               y:{{grid:{{display:false}},border:{{display:false}}}}}}
    }},
    plugins:[{{afterDraw(c){{
      const ctx=c.ctx,xs=c.scales.x,ys=c.scales.y;
      const x0=xs.getPixelForValue(0);
      ctx.save();ctx.beginPath();ctx.moveTo(x0,ys.top);ctx.lineTo(x0,ys.bottom);
      ctx.strokeStyle='rgba(255,255,255,0.25)';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.stroke();
      ctx.restore();
    }}}}]
  }});
}})();</script>"""


def render_cn_macro(cn_macro: dict) -> str:
    usdcny      = cn_macro.get("usdcny")
    usdcny_date = cn_macro.get("usdcny_date") or cn_macro.get("date", "")
    cn10y       = cn_macro.get("cn10y")
    lpr         = cn_macro.get("lpr")

    usdcny_left = pin_pct(usdcny, 6.5, 7.5)
    cn10y_left  = pin_pct(cn10y, 0, 6) if cn10y else "50%"

    if usdcny and usdcny > 7.25:
        usdcny_badge = '<span class="badge b-dn">人民币偏弱</span>'
        usdcny_col   = "dn"
    elif usdcny and usdcny < 7.0:
        usdcny_badge = '<span class="badge b-up">人民币偏强</span>'
        usdcny_col   = "up"
    else:
        usdcny_badge = '<span class="badge b-neutral">中性</span>'
        usdcny_col   = "nt"

    lpr_line = f"&nbsp;·&nbsp; LPR(1Y): <strong>{fmt(lpr,2,suffix='%')}</strong>" if lpr else ""

    return f"""
<div class="grid-2 fade-in">
  <div class="card card-sm gauge">
    <p class="gauge-name">美元/人民币 USD/CNY {usdcny_badge}</p>
    <p class="gauge-val {usdcny_col}">{fmt(usdcny, 4, fallback="N/A")}</p>
    <p class="gauge-date">{usdcny_date}{lpr_line}</p>
    <div class="gbar">
      <div class="gs" style="width:25%;background:#22d87c"></div>
      <div class="gs" style="width:50%;background:#f5a623"></div>
      <div class="gs" style="width:25%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{usdcny_left}"></div></div>
    <div class="glbls"><span>6.5 人民币强</span><span>7.0 中性</span><span>7.5 人民币弱</span></div>
  </div>
  <div class="card card-sm gauge">
    <p class="gauge-name">中国10年期国债收益率 <span class="badge b-neutral">{'实时' if cn10y else 'N/A'}</span></p>
    <p class="gauge-val nt">{fmt(cn10y, 2, suffix="%", fallback="N/A")}</p>
    <p class="gauge-date">{cn_macro.get("cn10y_date","") or cn_macro.get("date","")}</p>
    <div class="gbar">
      <div class="gs" style="width:33%;background:#22d87c"></div>
      <div class="gs" style="width:34%;background:#f5a623"></div>
      <div class="gs" style="width:33%;background:#f05252"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{cn10y_left}"></div></div>
    <div class="glbls"><span>&lt;2% 低</span><span>2–3.5% 正常</span><span>&gt;3.5% 偏高</span></div>
  </div>
</div>"""


def render_cn_northbound(nb: dict) -> str:
    net   = nb.get("net_flow")
    sh    = nb.get("sh_flow")
    sz    = nb.get("sz_flow")
    date  = nb.get("date", "")
    is_in = net is not None and net >= 0

    if net is None:
        badge = '<span class="badge b-neutral">暂无数据</span>'
        val_col = "nt"
    elif net >= 20:
        badge = '<span class="badge b-up">大幅净买入</span>'
        val_col = "up"
    elif net >= 0:
        badge = '<span class="badge b-up">净买入</span>'
        val_col = "up"
    elif net >= -20:
        badge = '<span class="badge b-dn">净卖出</span>'
        val_col = "dn"
    else:
        badge = '<span class="badge b-dn">大幅净卖出</span>'
        val_col = "dn"

    net_str  = (("+" if is_in else "") + fmt(net, 2, suffix=" 亿元")) if net is not None else "N/A"
    sh_str   = (("+" if sh and sh >= 0 else "") + fmt(sh, 2) + " 亿") if sh is not None else "—"
    sz_str   = (("+" if sz and sz >= 0 else "") + fmt(sz, 2) + " 亿") if sz is not None else "—"

    # Simple bar gauge: net flow range -200 to +200 亿
    left = pin_pct(net, -200, 200)
    return f"""
<div class="card card-sm gauge fade-in">
  <p class="gauge-name">北向资金净流入 (沪深港通) {badge}</p>
  <p class="gauge-val {val_col}">{net_str}</p>
  <p class="gauge-date">{date} &nbsp;·&nbsp; 沪股通: {sh_str} &nbsp;|&nbsp; 深股通: {sz_str}</p>
  <div class="gbar">
    <div class="gs" style="width:50%;background:#f05252"></div>
    <div class="gs" style="width:50%;background:#22d87c"></div>
  </div>
  <div class="mwrap"><div class="mkr" style="left:{left}"></div></div>
  <div class="glbls"><span>–200亿 大幅卖出</span><span>0 中性</span><span>+200亿 大幅买入</span></div>
  <p style="font-size:9px;color:var(--text3);margin-top:6px">
    北向资金 = 外资通过沪深港通买卖A股的净额，正值表示外资净买入A股，是A股市场重要的"聪明钱"风向标
  </p>
</div>"""


def render_cn_margin(mg: dict) -> str:
    bal   = mg.get("balance")       # 万亿元
    sh    = mg.get("sh_balance")
    sz    = mg.get("sz_balance")
    trend = mg.get("trend") or []
    date  = mg.get("date", "")

    # Typical range: 1.5 – 3.5 万亿
    left = pin_pct(bal, 1.5, 3.5)
    if bal is None:
        badge = '<span class="badge b-neutral">暂无数据</span>'
        val_col = "nt"
    elif bal >= 3.0:
        badge = '<span class="badge b-dn">高杠杆警戒</span>'
        val_col = "dn"
    elif bal >= 2.5:
        badge = '<span class="badge b-warn">杠杆偏高</span>'
        val_col = "wn"
    elif bal >= 1.8:
        badge = '<span class="badge b-neutral">正常</span>'
        val_col = "nt"
    else:
        badge = '<span class="badge b-up">杠杆偏低</span>'
        val_col = "up"

    bal_str = fmt(bal, 4, suffix=" 万亿元") if bal else "N/A"
    sub = f"沪市: {fmt(sh,4)} 万亿 &nbsp;|&nbsp; 深市: {fmt(sz,4)} 万亿" if sh and sz else date

    js = f"sparkline('cnMarginChart',{json.dumps(trend)},'#f5a623','rgba(245,166,35,0.12)');" if trend else ""

    return f"""
<div class="card card-sm gauge fade-in">
  <p class="gauge-name">融资融券余额 (沪+深) {badge}</p>
  <p class="gauge-val {val_col}">{bal_str}</p>
  <p class="gauge-date">{sub}</p>
  <div class="gbar">
    <div class="gs" style="width:25%;background:#22d87c"></div>
    <div class="gs" style="width:35%;background:#f5a623"></div>
    <div class="gs" style="width:25%;background:#f07050"></div>
    <div class="gs" style="width:15%;background:#f05252"></div>
  </div>
  <div class="mwrap"><div class="mkr" style="left:{left}"></div></div>
  <div class="glbls"><span>&lt;1.5 低杠杆</span><span>1.5–2.5 正常</span><span>2.5–3.5 偏高</span><span>&gt;3.5 极高</span></div>
  <div style="height:46px;margin:8px -14px -12px;overflow:hidden"><canvas id="cnMarginChart"></canvas></div>
  <p style="font-family:'DM Mono',monospace;font-size:8px;color:var(--text3);text-align:center;padding:2px 0 2px">12-Month Trend</p>
  <p style="font-size:9px;color:var(--text3);margin-top:2px">融资余额历史峰值 ~2.27万亿 (2015年6月崩盘前)</p>
</div>
<script>(function(){{ {js} }})();</script>"""


def render_cn_pmi(pmi: dict) -> str:
    mfg       = pmi.get("mfg")
    svc       = pmi.get("svc")
    mfg_prev  = pmi.get("mfg_prev")
    svc_prev  = pmi.get("svc_prev")
    month     = pmi.get("month", "")
    mfg_trend = pmi.get("mfg_trend") or []
    svc_trend = pmi.get("svc_trend") or []

    def pmi_badge(v):
        if v is None: return '<span class="badge b-neutral">N/A</span>'
        if v >= 52:   return '<span class="badge b-up">强劲扩张</span>'
        if v >= 50:   return '<span class="badge b-up">扩张</span>'
        if v >= 48:   return '<span class="badge b-warn">收缩</span>'
        return             '<span class="badge b-dn">显著收缩</span>'

    def pmi_col(v):
        if v is None: return "nt"
        return "up" if v >= 50 else "dn"

    def trend_arrow(cur, prev):
        if cur is None or prev is None: return ""
        return " ▲" if cur > prev else " ▽" if cur < prev else " ─"

    mfg_left = pin_pct(mfg, 40, 60)
    svc_left = pin_pct(svc, 40, 60)

    js_mfg = f"sparkline('cnPmiMfgChart',{json.dumps(mfg_trend)},'#22d87c','rgba(34,216,124,0.1)');" if mfg_trend else ""
    js_svc = f"sparkline('cnPmiSvcChart',{json.dumps(svc_trend)},'#4e9eff','rgba(78,158,255,0.1)');" if svc_trend else ""

    def gauge_card(label, val, prev, left, col, badge, canvas, clr, fill):
        val_str = fmt(val, 1, fallback="N/A") + trend_arrow(val, prev)
        sub = f"前值 {fmt(prev,1)} &nbsp;·&nbsp; {month}"
        return f"""
  <div class="card card-sm gauge">
    <p class="gauge-name">{label} {badge}</p>
    <p class="gauge-val {col}">{val_str}</p>
    <p class="gauge-date">{sub}</p>
    <div class="gbar">
      <div class="gs" style="width:30%;background:#f05252"></div>
      <div class="gs" style="width:20%;background:#556"></div>
      <div class="gs" style="width:25%;background:#7aca56"></div>
      <div class="gs" style="width:25%;background:#22d87c"></div>
    </div>
    <div class="mwrap"><div class="mkr" style="left:{left}"></div></div>
    <div class="glbls"><span>收缩&lt;50</span><span>~50荣枯线</span><span>50–52扩张</span><span>&gt;52强劲</span></div>
    <div style="height:40px;margin:6px -14px -12px;overflow:hidden"><canvas id="{canvas}"></canvas></div>
    <p style="font-family:'DM Mono',monospace;font-size:8px;color:var(--text3);text-align:center;padding:2px 0 2px">12-Month Trend</p>
  </div>"""

    mfg_card = gauge_card("制造业PMI (NBS官方)", mfg, mfg_prev, mfg_left,
                          pmi_col(mfg), pmi_badge(mfg), "cnPmiMfgChart", "#22d87c", "rgba(34,216,124,0.1)")
    svc_card = gauge_card("非制造业PMI (NBS官方)", svc, svc_prev, svc_left,
                          pmi_col(svc), pmi_badge(svc), "cnPmiSvcChart", "#4e9eff", "rgba(78,158,255,0.1)")

    return f"""
<div class="grid-2 fade-in">
  {mfg_card}
  {svc_card}
</div>
<script>(function(){{ {js_mfg} {js_svc} }})();</script>"""


def render_moutai(mt: dict) -> str:
    price = mt.get("price")
    chg   = mt.get("change_pct")
    rsi   = mt.get("rsi")
    ytd   = mt.get("ytd")
    trend = mt.get("trend") or []
    date  = mt.get("date", "")

    price_str = fmt(price, 2, prefix="¥", fallback="N/A")
    sign  = "▲" if chg and chg >= 0 else "▽"
    chg_col = "up" if chg and chg >= 0 else "dn"
    chg_str = f"{sign} {fmt(abs(chg) if chg else 0, 2)}%" if chg is not None else ""
    ytd_str = (("+" if ytd and ytd >= 0 else "") + fmt(ytd, 1, suffix="%")) if ytd is not None else "N/A"

    # Folk interpretation
    if ytd and ytd >= 15:
        interp = "商务消费旺盛，市场风险偏好高 — 历史上茅台大涨时A股往往处于牛市区间"
        interp_col = "#22d87c"
    elif ytd and ytd >= 0:
        interp = "消费情绪平稳，市场处于正常状态"
        interp_col = "#8b909e"
    elif ytd and ytd >= -15:
        interp = "消费承压或政策限制，需关注宏观需求走弱信号"
        interp_col = "#f5a623"
    else:
        interp = "⚠️ 消费显著下滑 — 类似2012年反腐周期，需高度警惕经济下行压力"
        interp_col = "#f05252"

    js = f"sparkline('moutaiChart',{json.dumps(trend)},'#c8a96e','rgba(200,169,110,0.15)');" if trend else ""

    return f"""
<div class="card fade-in" style="padding-bottom:0">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:10px">
    <div>
      <p style="font-size:9px;font-family:'DM Mono',monospace;color:var(--accent);letter-spacing:.1em;margin-bottom:4px">
        🍶 民间信心指数 · FOLK CONFIDENCE PROXY
      </p>
      <p style="font-size:14px;font-weight:700;margin-bottom:2px">贵州茅台 Kweichow Moutai</p>
      <p style="font-size:10px;font-family:'DM Mono',monospace;color:var(--text3)">600519.SS · A股 · 消费品龙头</p>
    </div>
    <div style="text-align:right">
      <p style="font-family:'DM Serif Display',serif;font-size:26px;line-height:1">{price_str}</p>
      <p style="font-size:13px;color:var(--{chg_col});margin-top:2px">{chg_str}</p>
    </div>
  </div>
  <div style="display:flex;gap:16px;margin-bottom:10px;flex-wrap:wrap">
    <div><p style="font-size:10px;color:var(--text3)">YTD</p>
         <p style="font-size:14px;font-weight:600;color:var(--{pct_color(ytd)})">{ytd_str}</p></div>
    <div><p style="font-size:10px;color:var(--text3)">RSI(14)</p>
         <p style="font-size:14px;font-weight:600;class="{rsi_color(rsi)}">{fmt(rsi,1,fallback="N/A")} {rsi_badge(rsi)}</p></div>
    <div style="flex:1;min-width:160px">
      <div style="background:rgba(200,169,110,0.08);border:1px solid rgba(200,169,110,0.2);
                  border-radius:8px;padding:8px 10px">
        <p style="font-size:10px;color:{interp_col};line-height:1.5">{interp}</p>
      </div>
    </div>
  </div>
  <div style="height:54px;margin:0 -16px -16px;overflow:hidden"><canvas id="moutaiChart"></canvas></div>
  <p style="font-family:'DM Mono',monospace;font-size:8px;color:var(--text3);text-align:center;padding:3px 0 3px">12-Month Trend</p>
</div>
<script>(function(){{ {js} }})();</script>"""


def sec_cn(label, title):
    return (f'<div class="sec" style="--accent:#f87171">'
            f'<span class="sec-num" style="color:#f87171;border-color:rgba(248,113,113,0.3)">{label}</span>'
            f'<span class="sec-title">{title}</span>'
            f'<div class="sec-line"></div></div>')


def render_cn_page(data: dict) -> str:
    cn_indices  = data.get("cn_indices", [])
    cn_sectors  = data.get("cn_sectors", [])
    cn_macro    = data.get("cn_macro", {})
    cn_nb       = data.get("cn_northbound", {})
    cn_mg       = data.get("cn_margin", {})
    cn_pmi      = data.get("cn_pmi", {})
    moutai      = data.get("moutai", {})

    return f"""
<div style="background:linear-gradient(135deg,rgba(220,38,38,0.1),rgba(220,38,38,0.03));
            border:1px solid rgba(248,113,113,0.2);border-radius:12px;
            padding:18px 22px;margin:48px 0 8px;display:flex;align-items:center;gap:14px">
  <span style="font-size:30px">🇨🇳</span>
  <div>
    <p style="font-family:'DM Serif Display',serif;font-size:20px;color:#f87171;margin-bottom:3px">中国A股市场</p>
    <p style="font-size:11px;color:var(--text2);font-family:'DM Mono',monospace;letter-spacing:.1em">
      CHINA A-SHARE MARKET INTELLIGENCE &nbsp;·&nbsp; {data.get("report_date","")}
    </p>
  </div>
</div>

{sec_cn("Ⓐ", "五大核心指数快照 — 上证 · 深证 · 创业板 · 沪深300 · 科创50")}
{render_cn_indices(cn_indices)}

{sec_cn("Ⓑ", "技术信号 RSI 概览 — 超买 / 超卖排名")}
{render_cn_rsi(cn_indices)}

{sec_cn("Ⓒ", "主要板块ETF表现 — A股8大板块 YTD")}
{render_cn_sectors(cn_sectors)}

{sec_cn("Ⓓ", "宏观参考指标 — 人民币汇率 · 国债收益率")}
{render_cn_macro(cn_macro)}

{sec_cn("Ⓔ", "北向资金 — 外资净流入 / 净流出 (沪深港通)")}
{render_cn_northbound(cn_nb)}

{sec_cn("Ⓕ", "融资融券余额 — 市场杠杆温度计")}
{render_cn_margin(cn_mg)}

{sec_cn("Ⓖ", "官方PMI — 制造业 · 非制造业 (NBS)")}
{render_cn_pmi(cn_pmi)}

{sec_cn("Ⓗ", "茅台信心指数 — 民间消费景气代理指标")}
{render_moutai(moutai)}
"""


# ─────────────────────────────────────────────
# FULL HTML ASSEMBLY
# ─────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>U.S. & A-Share Market Report — {report_date}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@400;500&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{{--bg:#0a0c0f;--bg2:#111318;--bg3:#181c23;--border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.12);--text:#e8eaf0;--text2:#8b909e;--text3:#555a68;--up:#22d87c;--dn:#f05252;--warn:#f5a623;--info:#4e9eff;--accent:#c8a96e}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:13px;line-height:1.5}}
.page-header{{background:linear-gradient(135deg,#0d0f14,#131720,#0e1119);border-bottom:1px solid var(--border2);padding:28px 32px 24px;position:relative;overflow:hidden}}
.page-header::before{{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 60% 80% at 80% 50%,rgba(200,169,110,0.06),transparent);pointer-events:none}}
.header-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap}}
.report-eyebrow{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}}
.report-title{{font-family:'DM Serif Display',serif;font-size:28px;line-height:1.15;margin-bottom:6px}}
.report-sub{{font-size:12px;color:var(--text2)}}
.report-date{{text-align:right}}
.date-num{{font-family:'DM Serif Display',serif;font-size:22px;color:var(--accent)}}
.date-day{{font-size:11px;color:var(--text3);font-family:'DM Mono',monospace}}
.header-sources{{margin-top:14px;font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);letter-spacing:.06em}}
.container{{max-width:1100px;margin:0 auto;padding:28px 24px 60px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
.sec{{display:flex;align-items:center;gap:10px;margin:32px 0 14px}}
.sec-num{{font-family:'DM Mono',monospace;font-size:10px;background:var(--bg3);border:1px solid var(--border2);color:var(--accent);padding:2px 8px;border-radius:4px;letter-spacing:.08em}}
.sec-title{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--text2)}}
.sec-line{{flex:1;height:1px;background:var(--border)}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;position:relative;overflow:hidden}}
.card-sm{{padding:12px 14px}}
.card-sub{{font-size:11px}}
.badge{{display:inline-block;font-size:9px;font-weight:600;padding:1px 7px;border-radius:3px;margin-left:5px;vertical-align:middle;letter-spacing:.04em;text-transform:uppercase}}
.b-up{{background:rgba(34,216,124,0.15);color:#22d87c}}
.b-dn{{background:rgba(240,82,82,0.15);color:#f05252}}
.b-warn{{background:rgba(245,166,35,0.15);color:#f5a623}}
.b-info{{background:rgba(78,158,255,0.15);color:#4e9eff}}
.b-neutral{{background:rgba(255,255,255,0.06);color:#8b909e}}
.b-accent{{background:rgba(200,169,110,0.15);color:#c8a96e}}
.up{{color:#22d87c}}.dn{{color:#f05252}}.wn{{color:#f5a623}}.in{{color:#4e9eff}}.nt{{color:#8b909e}}.ac{{color:#c8a96e}}
.gauge-name{{font-size:12px;font-weight:500;margin-bottom:3px}}
.gauge-val{{font-size:18px;font-weight:600;margin-bottom:2px}}
.gauge-date{{font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);margin-bottom:10px}}
.gbar{{display:flex;height:7px;border-radius:4px;overflow:hidden}}
.gs{{height:100%}}
.mwrap{{position:relative;height:10px}}
.mkr{{position:absolute;width:2px;height:10px;background:var(--text);border-radius:1px;transform:translateX(-50%)}}
.glbls{{display:flex;justify-content:space-between;font-size:9px;color:var(--text3);margin-top:3px;font-family:'DM Mono',monospace}}
.rsi-gauge{{display:flex;align-items:flex-start;gap:8px;margin:8px 0}}
.rsi-lbl{{font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);flex-shrink:0;width:20px;margin-top:1px}}
.rsi-body{{flex:1;min-width:0}}
.rsi-bar{{height:6px;border-radius:3px;overflow:hidden;display:flex}}
.rsi-pin-wrap{{position:relative;height:8px}}
.rsi-pin{{position:absolute;top:0;width:2px;height:8px;background:var(--text);border-radius:1px;transform:translateX(-50%)}}
.rsi-ends{{display:flex;justify-content:space-between;font-size:8px;color:var(--text3);margin-top:1px;font-family:'DM Mono',monospace}}
.rsi-val{{font-family:'DM Mono',monospace;font-size:12px;font-weight:500;flex-shrink:0;width:28px;text-align:right}}
.sparkline-area{{height:72px;margin:10px -16px -16px;position:relative;overflow:hidden}}
.sparkline-lbl{{position:absolute;bottom:4px;width:100%;text-align:center;font-size:9px;color:var(--text3);font-family:'DM Mono',monospace}}
.sector-table{{width:100%;border-collapse:collapse;font-size:12px}}
.sector-table th{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}}
.sector-table td{{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:middle}}
.sector-table tr:last-child td{{border-bottom:none}}
.sector-table tr:hover td{{background:rgba(255,255,255,0.02)}}
.bar-bg{{height:5px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:visible;position:relative;width:80px}}
.bar-fill{{height:100%;border-radius:3px;position:absolute;top:0}}
.pill{{display:inline-block;font-size:9px;font-weight:600;padding:1px 6px;border-radius:3px;text-transform:uppercase;letter-spacing:.04em}}
.watch-item{{display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}}
.watch-item:last-child{{border-bottom:none}}
.watch-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:4px}}
.watch-name{{font-size:12px;font-weight:500;flex:1.2;min-width:0}}
.watch-note{{font-size:11px;color:var(--text2);flex:2;min-width:0;line-height:1.4}}
.watch-date{{font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);white-space:nowrap}}
.strategy{{background:linear-gradient(135deg,rgba(200,169,110,0.08),rgba(200,169,110,0.03));border:1px solid rgba(200,169,110,0.2);border-radius:12px;padding:16px 20px;display:flex;gap:14px;align-items:flex-start}}
.strategy-icon{{font-size:20px;flex-shrink:0}}
.strategy-title{{font-size:13px;font-weight:600;color:var(--accent);margin-bottom:4px}}
.strategy-body{{font-size:12px;color:#c8b87e;line-height:1.6}}
.doughcon-row{{display:flex;gap:6px;margin:10px 0}}
.dc-seg{{flex:1;border-radius:6px;padding:7px 4px;text-align:center}}
.dc-seg-num{{font-size:13px;font-weight:700}}
.dc-seg-txt{{font-size:9px;margin-top:2px}}
.loc-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}}
.loc-card{{background:var(--bg3);border-radius:8px;padding:8px 10px}}
.loc-name{{font-size:11px;font-weight:500;margin-bottom:1px}}
.loc-dist{{font-size:9px;color:var(--text3);font-family:'DM Mono',monospace}}
.loc-pct{{font-size:13px;font-weight:600;color:var(--up);margin-top:4px}}
.loc-bar{{height:3px;background:rgba(255,255,255,0.07);border-radius:2px;margin-top:4px;overflow:hidden}}
.loc-bar-fill{{height:100%;border-radius:2px;background:var(--up)}}
.tl-item{{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)}}
.tl-item:last-child{{border-bottom:none}}
.tl-date{{font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);width:80px;flex-shrink:0}}
.tl-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.tl-desc{{font-size:11px;flex:1;color:var(--text2)}}
.tl-val{{font-size:11px;font-weight:600;white-space:nowrap}}
.com-card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px;overflow:hidden}}
.com-icon{{font-size:20px;margin-bottom:5px}}
.com-name{{font-size:12px;font-weight:600}}
.com-unit{{font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);margin-bottom:7px}}
.com-price{{font-size:20px;font-weight:600;line-height:1.1;margin-bottom:2px}}
.com-ytd{{font-size:11px;font-weight:500;margin-bottom:7px}}
.com-key{{font-size:10px;color:var(--text2);line-height:1.5;margin-bottom:8px}}
.com-spark{{height:46px;margin:0 -14px -14px;overflow:hidden;position:relative}}
.com-spark-lbl{{font-family:'DM Mono',monospace;font-size:8px;color:var(--text3);text-align:center;padding:2px 0 3px}}
.semi-card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px;overflow:hidden}}
.semi-spark{{height:56px;margin:8px -14px -14px;overflow:hidden}}
.semi-spark-lbl{{font-family:'DM Mono',monospace;font-size:8px;color:var(--text3);text-align:center;padding:2px 0 3px}}
.semi-detail{{background:var(--bg3);border-radius:8px;padding:10px;margin-top:8px;font-size:10px;color:var(--text2);line-height:1.6}}
.chart-wrap{{position:relative}}
.chart-wrap-md{{height:270px;margin-bottom:16px}}
.chart-wrap-rsi{{height:260px;margin-bottom:16px}}
.page-footer{{background:var(--bg2);border-top:1px solid var(--border);padding:20px 32px;text-align:center;font-family:'DM Mono',monospace;font-size:9px;color:var(--text3);letter-spacing:.06em;line-height:1.8}}
hr.div{{border:none;border-top:1px solid var(--border);margin:28px 0}}
.fade-in{{opacity:0;transform:translateY(16px);animation:fadeUp .5s ease forwards}}
@keyframes fadeUp{{to{{opacity:1;transform:translateY(0)}}}}
.fade-in:nth-child(1){{animation-delay:.05s}}.fade-in:nth-child(2){{animation-delay:.1s}}
.fade-in:nth-child(3){{animation-delay:.15s}}.fade-in:nth-child(4){{animation-delay:.2s}}
.fade-in:nth-child(5){{animation-delay:.25s}}.fade-in:nth-child(6){{animation-delay:.3s}}
@media(max-width:900px){{.grid-3{{grid-template-columns:1fr 1fr}}}}
@media(max-width:768px){{.grid-2,.grid-3{{grid-template-columns:1fr}}.report-title{{font-size:22px}}.container{{padding:16px 14px 40px}}.page-header{{padding:20px 16px}}}}
</style>
</head>
<body>
<header class="page-header">
  <div class="header-top">
    <div>
      <p class="report-eyebrow">Weekly Briefing · United States &amp; China A-Share</p>
      <h1 class="report-title">Market Sentiment &amp; Macro Intelligence Report</h1>
      <p class="report-sub">U.S. Indices · Volatility · Macro · Sectors · Semis · Commodities · PizzINT &nbsp;|&nbsp; 🇨🇳 A股指数 · 板块ETF · 人民币</p>
    </div>
    <div class="report-date">
      <p class="date-num">{report_date}</p>
      <p class="date-day">{report_day}</p>
    </div>
  </div>
  <p class="header-sources">Sources: yfinance · FRED · alternative.me · pizzint.watch · CBOE · BLS · ISM · CME</p>
</header>
<div class="container">

{sec_pizza}

<div class="sec"><span class="sec-num">②</span><span class="sec-title">Index Snapshot — 10-Year Trend</span><div class="sec-line"></div></div>
{sec_indices}

<div class="sec"><span class="sec-num">③</span><span class="sec-title">Sentiment &amp; Volatility Gauges</span><div class="sec-line"></div></div>
{sec_sentiment}

<hr class="div">
{sec_macro}

<hr class="div">
<div class="sec"><span class="sec-num">⑨</span><span class="sec-title">S&P 500 Sector Performance — GICS 10 Sectors YTD</span><div class="sec-line"></div></div>
{sec_sectors}

<div class="sec"><span class="sec-num">⑨-B</span><span class="sec-title">Semiconductor Special Focus — 半导体专题</span><div class="sec-line"></div></div>
{sec_semi}

<hr class="div">
<div class="sec"><span class="sec-num">⑩</span><span class="sec-title">Sector RSI Summary — 超买 / 超卖排名</span><div class="sec-line"></div></div>
<div class="card fade-in"><div class="chart-wrap chart-wrap-rsi"><canvas id="rsiChart"></canvas></div></div>

<hr class="div">
<div class="sec"><span class="sec-num">⑪</span><span class="sec-title">Commodities — 黄金·白银·稀土·煤炭·棉花·大豆</span><div class="sec-line"></div></div>
{sec_commodities}

<hr class="div">
<div class="sec"><span class="sec-num">⑫</span><span class="sec-title">Priority Watchlist &amp; Strategy</span><div class="sec-line"></div></div>
{sec_watchlist}

<hr class="div">
<div class="sec"><span class="sec-num">⑬</span><span class="sec-title">AI 市场情报解读 — Powered by DeepSeek</span><div class="sec-line"></div></div>
{sec_ai}

{sec_cn_page}

</div>
<footer class="page-footer">
  <p>DATA SOURCES: yfinance · FRED (Federal Reserve) · alternative.me · pizzint.watch · CBOE · BLS · ISM · CME · SSE · SZSE</p>
  <p>RSI及技术指标由实时数据计算 · 大宗商品趋势图基于实际价格数据 · 本报告为自动生成，仅供信息参考，不构成任何投资建议</p>
  <p style="margin-top:6px;color:rgba(255,255,255,0.15)">Auto-generated · {generated_at}</p>
</footer>
<script>
Chart.defaults.color='rgba(255,255,255,0.45)';
Chart.defaults.borderColor='rgba(255,255,255,0.07)';
function sparkline(id,data,color,fill){{
  const el=document.getElementById(id);if(!el||!data.length)return;
  new Chart(el,{{type:'line',
    data:{{labels:data.map((_,i)=>i),datasets:[{{data,borderColor:color,borderWidth:1.5,pointRadius:0,tension:.4,fill:true,backgroundColor:fill}}]}},
    options:{{responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{{legend:{{display:false}},tooltip:{{enabled:false}}}},
      scales:{{x:{{display:false}},y:{{display:false}}}}}}
  }});
}}
sparkline('spxChart',{spx_trend},'#22d87c','rgba(34,216,124,0.12)');
sparkline('ndxChart',{ndx_trend},'#4e9eff','rgba(78,158,255,0.12)');
sparkline('soxChart',{sox_trend},'#4e9eff','rgba(78,158,255,0.12)');
sparkline('soxxChart',{soxx_trend},'#4e9eff','rgba(78,158,255,0.12)');
</script>
</body>
</html>"""


def generate(data: dict) -> str:
    spx = data.get("spx", {})
    ndx = data.get("ndx", {})
    vol = data.get("volatility", {})
    fg = data.get("fear_greed", {})
    macro = data.get("macro", {})
    fw = data.get("fedwatch", {})
    sectors = data.get("sectors", [])
    semi = data.get("semiconductor", {})
    comms = data.get("commodities", [])
    pizza = data.get("pizza", {})

    return HTML_TEMPLATE.format(
        report_date=data.get("report_date", ""),
        report_day=data.get("report_day", ""),
        generated_at=data.get("generated_at", ""),
        sec_pizza=f'<div class="sec"><span class="sec-num">①</span>'
                  f'<span class="sec-title">Pentagon Pizza Index — OSINT Geopolitical Tension</span>'
                  f'<div class="sec-line"></div></div>' + render_pizza(pizza),
        sec_indices=render_indices(spx, ndx),
        sec_sentiment=render_sentiment(vol, fg, spx, ndx),
        sec_macro=render_macro(macro, fw),
        sec_sectors=render_sectors(sectors),
        sec_semi=render_semiconductor(semi),
        sec_commodities=render_commodities(comms),
        sec_watchlist=render_watchlist(data),
        sec_ai=render_ai_analysis(data.get("ai_analysis") or {}),
        sec_cn_page=render_cn_page(data),
        spx_trend=json.dumps(spx.get("trend_10y") or []),
        ndx_trend=json.dumps(ndx.get("trend_10y") or []),
        sox_trend=json.dumps(semi.get("sox_trend") or []),
        soxx_trend=json.dumps(semi.get("soxx_trend") or []),
    )


if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "..", "output", "data.json")
    with open(data_path) as f:
        data = json.load(f)
    html = generate(data)
    out_path = os.path.join(os.path.dirname(__file__), "..", "output", "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report written to {out_path}")
