"""
generate_analysis.py
Calls DeepSeek API to generate a bilingual market intelligence commentary
based on the fully-fetched data dict.

Required env var:
    DEEPSEEK_API_KEY  — your DeepSeek API key (sk-...)

Model used: deepseek-chat (DeepSeek-V3), which is extremely cost-efficient.
Estimated cost per weekly run: ~$0.002 (input ~2K tokens + output ~600 tokens).
"""

import os
import json
import logging

log = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL             = "deepseek-chat"
MAX_TOKENS        = 800


def _build_prompt(data: dict) -> str:
    """Summarise the key metrics into a concise context string for the LLM."""

    def v(x, decimals=2, fallback="N/A"):
        try:
            return f"{float(x):.{decimals}f}" if x is not None else fallback
        except (TypeError, ValueError):
            return fallback

    def pct(x, fallback="N/A"):
        try:
            s = f"{float(x):+.2f}%" if x is not None else fallback
            return s
        except (TypeError, ValueError):
            return fallback

    spx  = data.get("spx", {})
    ndx  = data.get("ndx", {})
    vol  = data.get("volatility", {})
    fg   = data.get("fear_greed", {})
    mac  = data.get("macro", {})
    pizza = data.get("pizza", {})
    sectors = sorted(data.get("sectors", []), key=lambda s: s.get("ytd") or 0, reverse=True)
    comms   = data.get("commodities", [])
    cn_idx  = data.get("cn_indices", [])
    cn_nb   = data.get("cn_northbound", {})
    cn_mg   = data.get("cn_margin", {})
    cn_pmi  = data.get("cn_pmi", {})
    moutai  = data.get("moutai", {})
    semi    = data.get("semiconductor", {})

    top_sectors = sectors[:3]
    bot_sectors = sectors[-3:]
    gold   = next((c for c in comms if c["symbol"] == "GC=F"), {})
    silver = next((c for c in comms if c["symbol"] == "SI=F"), {})

    lines = [
        f"=== 报告日期: {data.get('report_date','N/A')} ===",
        "",
        "【美股指数】",
        f"S&P 500:    {v(spx.get('price'))}  日变动 {pct(spx.get('change_pct'))}  YTD {pct(spx.get('ytd'))}  RSI {v(spx.get('rsi'))}  P/E {v(spx.get('pe'))}",
        f"Nasdaq 100: {v(ndx.get('price'))}  日变动 {pct(ndx.get('change_pct'))}  YTD {pct(ndx.get('ytd'))}  RSI {v(ndx.get('rsi'))}  P/E {v(ndx.get('pe'))}",
        f"VIX: {v(vol.get('vix'))}  VXN: {v(vol.get('vxn'))}  CNN Fear&Greed: {fg.get('value','N/A')} ({fg.get('label','N/A')})",
        "",
        "【美股板块 YTD Top3 / Bottom3】",
        "领涨: " + " | ".join(f"{s['symbol']} {pct(s.get('ytd'))} RSI={v(s.get('rsi'),1)}" for s in top_sectors),
        "领跌: " + " | ".join(f"{s['symbol']} {pct(s.get('ytd'))} RSI={v(s.get('rsi'),1)}" for s in bot_sectors),
        "",
        "【半导体】",
        f"SOXX: ${v(semi.get('soxx_price'))}  YTD {pct(semi.get('soxx_ytd'))}  RSI {v(semi.get('soxx_rsi'))}",
        "",
        "【宏观数据】",
        f"Fed Funds Rate: {v(mac.get('fed_rate'))}%  10Y Treasury: {v(mac.get('t10y'))}%  DXY: {v(mac.get('dxy'))}",
        f"CPI(YoY): {v(mac.get('cpi_yoy'))}%  Core CPI: {v(mac.get('core_cpi_yoy'))}%",
        f"NFP: {'+' if (mac.get('nfp_change') or 0) >= 0 else ''}{v(mac.get('nfp_change'),0)}K  失业率: {v(mac.get('unrate'))}%",
        f"ISM制造业PMI: {v(mac.get('ism_mfg'))}  ISM服务业PMI: {v(mac.get('ism_svc'))}",
        "",
        "【大宗商品】",
        f"黄金: ${v(gold.get('price'))} YTD {pct(gold.get('ytd'))} RSI {v(gold.get('rsi'),1)}",
        f"白银: ${v(silver.get('price'))} YTD {pct(silver.get('ytd'))} RSI {v(silver.get('rsi'),1)}",
        "",
        "【Pentagon Pizza Index】",
        f"DOUGHCON 等级: {pizza.get('level','N/A')} ({pizza.get('status','N/A')})",
        "",
        "【中国A股指数】",
    ]
    for idx in cn_idx:
        lines.append(
            f"{idx.get('name_cn','')}: {v(idx.get('price'))}  "
            f"日变动 {pct(idx.get('change_pct'))}  YTD {pct(idx.get('ytd'))}  RSI {v(idx.get('rsi'),1)}"
        )
    lines += [
        "",
        "【A股关键指标】",
        f"北向资金净流入: {'+' if (cn_nb.get('net_flow') or 0) >= 0 else ''}{v(cn_nb.get('net_flow'))} 亿元  "
        f"(沪 {v(cn_nb.get('sh_flow'))} / 深 {v(cn_nb.get('sz_flow'))})",
        f"融资融券余额: {v(cn_mg.get('balance'))} 万亿元",
        f"官方PMI: 制造业 {v(cn_pmi.get('mfg'),1)} (前值 {v(cn_pmi.get('mfg_prev'),1)})  "
        f"非制造业 {v(cn_pmi.get('svc'),1)} (前值 {v(cn_pmi.get('svc_prev'),1)})",
        f"茅台(600519): ¥{v(moutai.get('price'))} YTD {pct(moutai.get('ytd'))} RSI {v(moutai.get('rsi'),1)}",
    ]
    return "\n".join(lines)


def run(data: dict) -> dict:
    """
    Generate AI market commentary via DeepSeek.
    Returns a dict with keys: 'commentary', 'model', 'tokens_used', 'error'.
    Always returns gracefully — never raises.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        log.info("DEEPSEEK_API_KEY not set — skipping AI analysis.")
        return {"commentary": None, "model": None, "tokens_used": 0, "error": "no_api_key"}

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai package not installed — skipping AI analysis.")
        return {"commentary": None, "model": None, "tokens_used": 0, "error": "openai_not_installed"}

    context = _build_prompt(data)

    system_prompt = (
        "你是一位专业的量化金融分析师，擅长解读美股和中国A股市场数据。"
        "请根据用户提供的最新市场数据，撰写一份简洁、专业、有洞见的市场情报周报摘要。"
        "要求：\n"
        "1. 总长度控制在 250–350 字\n"
        "2. 结构：①美股技术面 ②宏观环境 ③A股关键信号 ④综合风险提示 ⑤本周策略建议\n"
        "3. 每段用一句话点明核心结论，避免平铺直叙\n"
        "4. 高亮异常数据（如RSI极值、PMI破线、北向大幅流出等）\n"
        "5. 语言：中文为主，专业术语可保留英文缩写（如 RSI、PMI、VIX）\n"
        "6. 不要输出标题，直接输出正文"
    )

    log.info(f"Calling DeepSeek API ({MODEL}) for market commentary ...")
    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": context},
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.6,
            stream=False,
        )
        commentary    = resp.choices[0].message.content.strip()
        tokens_used   = resp.usage.total_tokens if resp.usage else 0
        log.info(f"DeepSeek analysis done — {tokens_used} tokens used.")
        return {
            "commentary":   commentary,
            "model":        MODEL,
            "tokens_used":  tokens_used,
            "error":        None,
        }
    except Exception as e:
        log.warning(f"DeepSeek API call failed: {e}")
        return {"commentary": None, "model": MODEL, "tokens_used": 0, "error": str(e)}
