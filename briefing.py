import requests
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8734149271:AAHM5T5diwscMnfk7gzGkiRsP-uRbURVcjs"
TELEGRAM_CHAT_ID   = "623392672"
NEWS_API_KEY       = "425b2c8e51244bb9a09880eec07d56fb"
FRED_API_KEY       = "bea607ec27e9abfbb37124f5013e115e"
GROQ_API_KEY       = "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"

CRYPTO_WATCHLIST = {
    "bitcoin":     "BTC",
    "ethereum":    "ETH",
    "solana":      "SOL",
    "hyperliquid": "HYPE",
}

# Binance futures symbols for Open Interest
OI_SYMBOLS = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
}

FRED_SERIES = {
    "CPIAUCSL": "CPI (Inflation)",
    "UNRATE":   "Unemployment Rate",
    "GDP":      "GDP Growth",
    "FEDFUNDS": "Fed Funds Rate",
    "T10Y2Y":   "10Y-2Y Yield Spread",
    "PAYEMS":   "Non-Farm Payrolls",
    "UMCSENT":  "Consumer Sentiment",
    "NAPM":     "ISM Mfg PMI",
    "PCEPILFE": "Core PCE",
    "RSAFS":    "Retail Sales",
}

# Yahoo Finance tickers for global markets
MARKET_TICKERS = {
    "^GSPC":    ("S&P 500",  ""),
    "^IXIC":    ("Nasdaq",   ""),
    "^VIX":     ("VIX",      ""),
    "DX-Y.NYB": ("DXY",     ""),
    "GC=F":     ("Gold",     "$/oz"),
    "CL=F":     ("WTI Oil",  "$/bbl"),
    "^TNX":     ("US 10Y",   "%"),
}

DIVIDER = "─" * 26


# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    while text:
        chunk = text[:4000]
        text  = text[4000:]
        requests.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     chunk,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        })


# ── GLOBAL MARKETS (Yahoo Finance) ────────────────────────────────────────────
def get_market_snapshot():
    """Equities, VIX, DXY, Gold, Oil, 10Y yield via Yahoo Finance."""
    results = {}
    for ticker, (label, unit) in MARKET_TICKERS.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r   = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).json()
            closes = r["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
            if len(closes) >= 2:
                prev, curr = closes[-2], closes[-1]
                chg = ((curr - prev) / prev) * 100
            elif len(closes) == 1:
                curr, chg = closes[-1], None
            else:
                continue
            results[label] = {"price": curr, "change_pct": chg, "unit": unit}
        except Exception:
            pass
    return results


# ── CRYPTO ────────────────────────────────────────────────────────────────────
def get_crypto_prices():
    ids = ",".join(CRYPTO_WATCHLIST.keys())
    url = (
        f"https://api.coingecko.com/api/v3/simple/price?ids={ids}"
        "&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
    )
    try:
        return requests.get(url, timeout=10).json()
    except Exception:
        return {}


def get_eth_btc_ratio(prices):
    """ETH/BTC ratio — rising = alts gaining; falling = BTC dominance strengthening."""
    try:
        eth = prices.get("ethereum", {}).get("usd")
        btc = prices.get("bitcoin",  {}).get("usd")
        if eth and btc:
            return round(eth / btc, 5)
    except Exception:
        pass
    return None


def get_fear_greed():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()["data"][0]
        return d["value"], d["value_classification"]
    except Exception:
        return "N/A", "N/A"


def get_btc_dominance():
    try:
        r   = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()
        dom = r["data"]["market_cap_percentage"].get("bitcoin")
        return round(dom, 1) if dom else None
    except Exception:
        return None


def get_btc_funding_rate():
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1", timeout=10
        ).json()
        return float(r[0]["fundingRate"]) * 100
    except Exception:
        return None


def get_btc_ls_ratio():
    try:
        r = requests.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            "?symbol=BTCUSDT&period=1h&limit=1",
            timeout=10,
        ).json()
        return float(r[0]["longShortRatio"])
    except Exception:
        return None


def get_open_interest():
    """
    BTC and ETH Open Interest from Binance Futures.
    Returns { label: {oi_usd, oi_change_pct} }
    OI change is 1h delta from historical endpoint.
    """
    results = {}
    for symbol, label in OI_SYMBOLS.items():
        try:
            # Current OI (in contracts)
            oi_now = float(
                requests.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}", timeout=10)
                .json()["openInterest"]
            )
            # 1h historical for delta
            hist = requests.get(
                f"https://fapi.binance.com/futures/data/openInterestHist"
                f"?symbol={symbol}&period=1h&limit=2",
                timeout=10,
            ).json()
            if len(hist) >= 2:
                oi_prev   = float(hist[0]["sumOpenInterest"])
                oi_curr_h = float(hist[1]["sumOpenInterest"])
                chg_pct   = ((oi_curr_h - oi_prev) / oi_prev) * 100 if oi_prev else None
            else:
                chg_pct = None

            # Mark price to convert contracts → USD
            mark  = float(
                requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}", timeout=10)
                .json()["markPrice"]
            )
            oi_usd = oi_now * mark
            results[label] = {"oi_usd": oi_usd, "oi_change_pct": chg_pct}
        except Exception:
            pass
    return results


# ── MACRO ─────────────────────────────────────────────────────────────────────
def get_fred_latest(series_id):
    url = (
        f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}"
        f"&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=2"
    )
    try:
        data = requests.get(url, timeout=10).json().get("observations", [])
        if len(data) >= 2:
            return data[0]["value"], data[0]["date"], data[1]["value"]
        elif len(data) == 1:
            return data[0]["value"], data[0]["date"], None
        return None, None, None
    except Exception:
        return None, None, None


def get_all_macro():
    results = {}
    for series_id, label in FRED_SERIES.items():
        val, date, prev = get_fred_latest(series_id)
        results[label] = {"value": val, "date": date, "prev": prev}
    return results


def was_released_today(date_str):
    if not date_str:
        return False
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days <= 1
    except Exception:
        return False


# ── CALENDAR ──────────────────────────────────────────────────────────────────
def get_weekly_calendar():
    """Returns (by_day_dict, today_events_list). today_events is fed to AI to prevent hallucination."""
    try:
        r         = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10).json()
        by_day    = {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_ev  = []

        for e in r:
            if e.get("country", "").upper() != "USD":
                continue
            impact = e.get("impact", "").lower()
            if impact not in ("high", "medium"):
                continue
            try:
                event_date = e["date"][:10]
                day_key    = datetime.strptime(event_date, "%Y-%m-%d").strftime("%a %d %b")
            except Exception:
                continue

            badge  = " 🔴" if impact == "high" else " 🟡"
            detail = ""
            if e.get("forecast"): detail += f"  Fcst: {e['forecast']}"
            if e.get("previous"): detail += f"  Prev: {e['previous']}"

            entry = e.get("title", "Unknown") + badge + detail
            by_day.setdefault(day_key, []).append(entry)

            if event_date == today_str:
                today_ev.append(e.get("title", "Unknown") + detail)

        return by_day, today_ev
    except Exception:
        return {}, []


# ── POLYMARKET ────────────────────────────────────────────────────────────────
def get_polymarket_top():
    try:
        r       = requests.get("https://clob.polymarket.com/markets?active=true&closed=false", timeout=10).json()
        markets = r if isinstance(r, list) else r.get("data", [])
        mv      = [m for m in markets if float(m.get("volume", 0)) > 0]
        top     = sorted(mv, key=lambda x: float(x.get("volume", 0)), reverse=True)[:5]
        results = []
        for m in top:
            yes_price = None
            for t in m.get("tokens", []):
                if t.get("outcome", "").upper() == "YES":
                    yes_price = float(t.get("price", 0)) * 100
            results.append({
                "question": m.get("question", "Unknown"),
                "volume":   float(m.get("volume", 0)),
                "yes_prob": yes_price,
            })
        return results
    except Exception:
        return []


# ── NEWS ──────────────────────────────────────────────────────────────────────
def get_news(query, page_size=5):
    try:
        url = (
            f"https://newsapi.org/v2/everything?q={query}"
            f"&language=en&sortBy=publishedAt&pageSize={page_size}&apiKey={NEWS_API_KEY}"
        )
        return requests.get(url, timeout=10).json().get("articles", [])
    except Exception:
        return []


# ── AI ANALYSIS ───────────────────────────────────────────────────────────────
def get_groq_analysis(prices, fg_value, fg_label, macro,
                      macro_news, crypto_news, poly,
                      btc_dom, funding_rate, ls_ratio,
                      today_events, markets, oi_data, eth_btc_ratio):

    # Crypto prices block
    price_lines = []
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d  = prices.get(coin_id, {})
        p  = d.get("usd")
        c  = d.get("usd_24h_change")
        cs = f"{c:+.2f}%" if c is not None else "N/A"
        ps = f"${p:,.2f}" if p else "N/A"
        price_lines.append(f"{symbol}: {ps} ({cs})")
    if eth_btc_ratio:
        price_lines.append(f"ETH/BTC Ratio: {eth_btc_ratio:.5f}")

    # Global markets block
    market_lines = [
        f"{label}: {d['price']:,.2f} ({d['change_pct']:+.2f}%)" if d["change_pct"] is not None
        else f"{label}: {d['price']:,.2f}"
        for label, d in markets.items()
    ]

    # OI block
    oi_lines = []
    for label, d in oi_data.items():
        chg = f"{d['oi_change_pct']:+.2f}%" if d["oi_change_pct"] is not None else "N/A"
        oi_lines.append(f"{label} OI: ${d['oi_usd']/1e9:.2f}B (1h chg: {chg})")

    # Macro block
    macro_lines = []
    for label, d in macro.items():
        val, date, prev = d["value"], d["date"], d["prev"]
        if val and val != ".":
            try:
                diff = float(val) - float(prev) if prev and prev != "." else 0
                macro_lines.append(f"{label}: {float(val):.2f} ({diff:+.2f} vs prev) as of {date}")
            except Exception:
                macro_lines.append(f"{label}: {val} as of {date}")

    news_lines   = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})" for a in macro_news[:5]]
    crypto_lines = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})" for a in crypto_news[:5]]
    poly_lines   = [
        f"- {m['question'][:80]} | YES: {m['yes_prob']:.0f}% | Vol: ${m['volume']/1e6:.1f}M"
        for m in poly if m["yes_prob"]
    ] or ["No data"]

    extra = ""
    if btc_dom      is not None: extra += f"BTC Dominance: {btc_dom}%\n"
    if funding_rate is not None: extra += f"BTC Funding Rate: {funding_rate:.4f}%\n"
    if ls_ratio     is not None: extra += f"BTC Long/Short Ratio: {ls_ratio:.2f}\n"

    today_block = (
        "TODAY'S SCHEDULED US DATA RELEASES:\n" + "\n".join(f"- {e}" for e in today_events)
        if today_events else
        "TODAY'S SCHEDULED US DATA RELEASES: None scheduled today."
    )

    raw_data = "\n\n".join(filter(None, [
        "CRYPTO PRICES (24h):\n"  + "\n".join(price_lines),
        "GLOBAL MARKETS:\n"        + "\n".join(market_lines),
        "OPEN INTEREST:\n"         + "\n".join(oi_lines) if oi_lines else "",
        extra.strip(),
        f"FEAR & GREED: {fg_value} - {fg_label}",
        "US MACRO (FRED):\n"       + "\n".join(macro_lines),
        "MACRO HEADLINES:\n"       + "\n".join(news_lines),
        "CRYPTO HEADLINES:\n"      + "\n".join(crypto_lines),
        "POLYMARKET:\n"            + "\n".join(poly_lines),
        today_block,
    ]))

    prompt = f"""You are a Lead Macro Analyst reporting directly to Stanley Druckenmiller.

CRITICAL RULES:
1. For "TODAY DATA RELEASES TO WATCH" — reference ONLY events listed under \
"TODAY'S SCHEDULED US DATA RELEASES" in the raw data. If none are listed, say \
"No major US data releases scheduled today." Never invent events from memory.
2. For KEY LEVELS — use actual prices from the raw data as anchors. \
Round to clean levels (e.g. if BTC is $83,200, say "watch $85K / $80K"). Never fabricate prices.
3. Be sharp, not verbose. No filler. Every sentence must earn its place.

Output EXACTLY this structure — no extra headers or preamble:

Geopolitical: [one sentence — geopolitical or macro driver of current risk sentiment]
Technical: [one sentence — price action, key level broken, or liquidation event]
Macro Flow: [one sentence — capital rotation visible in the data]

THEME: [One sentence defining today's macro narrative]

CONVICTION: [BULLISH / NEUTRAL / BEARISH]  [X/10]
[One sentence justifying the score]

THE NARRATIVE GAP: [What retail believes vs. what the data actually shows]

THE SECOND-ORDER EFFECT: [What today's biggest story means 6-12 months out]

THE PIG TRADE: [Single highest-conviction asymmetric setup. Risk 1, Reward 5. Be specific.]

KEY LEVELS TO WATCH:
BTC: [support] / [resistance]
ETH: [support] / [resistance]
DXY: [level that matters and why — one clause]

WHAT CHANGES MY MIND: [The one data point, price level, or event that invalidates the thesis]

TODAY DATA RELEASES TO WATCH: [ONLY from calendar data provided. If none, say so.]

Raw data:
{raw_data}

Under 950 words. Think Druckenmiller, not CNBC."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model":       "llama-3.3-70b-versatile",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  1400,
                "temperature": 0.35,
            },
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI analysis unavailable: {e}"


# ── MESSAGE BUILDER ───────────────────────────────────────────────────────────
def build_message(prices, fg_value, fg_label, macro, poly, calendar,
                  btc_dom, funding_rate, ls_ratio, ai_text,
                  markets, oi_data, eth_btc_ratio):
    now   = datetime.now().strftime("%A, %d %b %Y")
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "☀️  <b>MORNING BRIEFING</b>",
        f"📅  <i>{now}  ·  Singapore  ·  6 AM</i>",
        DIVIDER, "",
    ]

    # ── Sentiment ─────────────────────────────────────────────────────────────
    fg_num   = int(fg_value) if str(fg_value).isdigit() else 50
    filled   = max(1, round(fg_num / 10))
    bar      = "█" * filled + "░" * (10 - filled)
    fg_emoji = (
        "🔴" if fg_num <= 25 else
        "🟠" if fg_num <= 45 else
        "🟡" if fg_num <= 55 else
        "🟢" if fg_num <= 75 else "💚"
    )
    lines += ["📊  <b>SENTIMENT</b>", f"{fg_emoji}  <b>{fg_value} — {fg_label}</b>  {bar}"]

    sub_parts = []
    if btc_dom is not None:
        sub_parts.append(f"BTC Dom: <b>{btc_dom}%</b>")
    if funding_rate is not None:
        fr_label = "Neutral" if abs(funding_rate) < 0.005 else ("Greed" if funding_rate > 0 else "Fear")
        sub_parts.append(f"Funding: <b>{funding_rate:+.4f}%</b> <i>({fr_label})</i>")
    if ls_ratio is not None:
        sub_parts.append(f"L/S: <b>{ls_ratio:.2f}</b>")
    if sub_parts:
        lines.append("  " + "  ·  ".join(sub_parts))

    # AI situational awareness bullets (shown here, stripped from AI section below)
    sent_bullets = []
    for keyword in ("Geopolitical:", "Technical:", "Macro Flow:"):
        for line in ai_text.split("\n"):
            if keyword in line:
                sent_bullets.append("  " + line.strip().lstrip("- *"))
                break
    if sent_bullets:
        lines += [""] + sent_bullets
    lines.append("")

    # ── Global Market Snapshot ────────────────────────────────────────────────
    lines += [DIVIDER, "🌍  <b>MARKET SNAPSHOT</b>", ""]

    def fmt_market_row(label, d):
        p = d["price"]
        c = d["change_pct"]
        if label == "VIX":
            ps = f"{p:.2f}"
        elif label in ("DXY", "US 10Y"):
            ps = f"{p:.3f}"
        elif label in ("Gold", "WTI Oil"):
            ps = f"${p:,.1f}"
        else:
            ps = f"{p:,.0f}"
        cs = (f"{'▲' if c >= 0 else '▼'} {abs(c):.2f}%") if c is not None else "—"
        return f"  <b>{label}</b>   {ps}   {cs}"

    eq_labels  = [l for l in ("S&P 500", "Nasdaq") if l in markets]
    mac_labels = [l for l in ("VIX", "DXY", "US 10Y", "Gold", "WTI Oil") if l in markets]

    if eq_labels:
        lines.append("<i>Equities</i>")
        for lbl in eq_labels:
            lines.append(fmt_market_row(lbl, markets[lbl]))
        lines.append("")
    if mac_labels:
        lines.append("<i>Macro Assets</i>")
        for lbl in mac_labels:
            lines.append(fmt_market_row(lbl, markets[lbl]))
        lines.append("")

    # ── Crypto Watchlist ──────────────────────────────────────────────────────
    lines += [DIVIDER, "💰  <b>CRYPTO WATCHLIST</b>", ""]
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d      = prices.get(coin_id, {})
        price  = d.get("usd")
        change = d.get("usd_24h_change")
        mcap   = d.get("usd_market_cap")
        ps     = f"${price:,.2f}" if price else "N/A"
        ms     = f"  <i>${mcap/1e9:.1f}B</i>" if mcap else ""
        cs     = (f"{'▲' if change >= 0 else '▼'} {abs(change):.2f}%") if change is not None else "—"
        lines.append(f"  <b>{symbol}</b>   {ps}   {cs}{ms}")

    if eth_btc_ratio is not None:
        lines.append(f"  <b>ETH/BTC</b>   {eth_btc_ratio:.5f}   <i>(alt season proxy)</i>")
    lines.append("")

    if oi_data:
        lines.append("<i>Open Interest — Binance Futures</i>")
        for label, d in oi_data.items():
            oi_b    = d["oi_usd"] / 1e9
            chg     = d["oi_change_pct"]
            chg_str = (f"  {'▲' if chg >= 0 else '▼'} {abs(chg):.2f}% 1h") if chg is not None else ""
            lines.append(f"  <b>{label} OI</b>   ${oi_b:.2f}B{chg_str}")
        lines.append("")

    # ── US Macro Data ─────────────────────────────────────────────────────────
    lines += [DIVIDER, "📉  <b>US MACRO DATA</b>", ""]
    new_releases = []
    for label, d in macro.items():
        val, date, prev = d["value"], d["date"], d["prev"]
        if val is None or val == ".":
            continue
        try:
            vf  = float(val)
            pf  = float(prev) if prev and prev != "." else None
            vs  = f"{vf:,.2f}"
            chg = ""
            if pf is not None:
                diff  = vf - pf
                arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "→")
                chg   = f"  {arrow} <i>{diff:+.2f}</i>"
        except Exception:
            vs, chg = str(val), ""
        fresh = "🆕 " if was_released_today(date) else ""
        if was_released_today(date):
            new_releases.append(label)
        lines.append(f"  {fresh}<b>{label}</b>:  {vs}{chg}  <i>({date})</i>")
    lines.append("")
    if new_releases:
        lines.append("🚨  <b>Released today:</b> " + ", ".join(new_releases))
    else:
        lines.append("⏰  <i>No new US data releases today</i>")
    lines.append("")

    # ── Economic Docket ───────────────────────────────────────────────────────
    lines += [DIVIDER, "📅  <b>ECONOMIC DOCKET — THIS WEEK</b>", ""]
    if calendar:
        for day, events in calendar.items():
            lines.append(f"  <b>{day}</b>")
            for ev in events[:4]:
                lines.append(f"    ‣ {ev}")
            lines.append("")
    else:
        lines += ["  <i>Calendar unavailable</i>", ""]

    # ── Polymarket ────────────────────────────────────────────────────────────
    lines += [DIVIDER, "🎯  <b>POLYMARKET — TOP BY VOLUME</b>", ""]
    if poly:
        for m in poly:
            vol = f"${m['volume']/1e6:.1f}M" if m["volume"] >= 1e6 else f"${m['volume']:,.0f}"
            yes = f"  <b>YES {m['yes_prob']:.0f}%</b>" if m["yes_prob"] else ""
            lines.append(f"  •  {m['question'][:72]}{yes}  <i>{vol}</i>")
    else:
        lines.append("  <i>Could not load Polymarket data</i>")
    lines.append("")

    # ── Druckenmiller Analysis ────────────────────────────────────────────────
    lines += [DIVIDER, "🧠  <b>DRUCKENMILLER ANALYSIS</b>", ""]

    # Strip situational bullets already shown in sentiment section above
    clean_ai, skip = [], False
    for line in ai_text.split("\n"):
        if any(k in line for k in ("Geopolitical:", "Technical:", "Macro Flow:")):
            skip = True
        if line.strip().startswith("THEME:"):
            skip = False
        if not skip:
            clean_ai.append(line)
    lines.append("\n".join(clean_ai).strip())
    lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += [DIVIDER, "🤖  <i>Yahoo Finance · CoinGecko · Binance · FRED · Polymarket · Groq AI</i>"]

    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Fetching data...")
    prices              = get_crypto_prices()
    markets             = get_market_snapshot()
    fg_value, fg_label  = get_fear_greed()
    macro               = get_all_macro()
    poly                = get_polymarket_top()
    macro_news          = get_news("Federal Reserve OR CPI OR inflation OR GDP OR recession OR FOMC OR ISM PMI", 5)
    crypto_news         = get_news("bitcoin OR ethereum OR crypto OR DeFi OR polymarket OR hyperliquid", 5)
    calendar, today_ev  = get_weekly_calendar()
    btc_dom             = get_btc_dominance()
    funding_rate        = get_btc_funding_rate()
    ls_ratio            = get_btc_ls_ratio()
    oi_data             = get_open_interest()
    eth_btc_ratio       = get_eth_btc_ratio(prices)

    print("Running AI analysis...")
    ai_text = get_groq_analysis(
        prices, fg_value, fg_label, macro,
        macro_news, crypto_news, poly,
        btc_dom, funding_rate, ls_ratio,
        today_ev, markets, oi_data, eth_btc_ratio,
    )

    print("Building message...")
    full_message = build_message(
        prices, fg_value, fg_label, macro, poly, calendar,
        btc_dom, funding_rate, ls_ratio, ai_text,
        markets, oi_data, eth_btc_ratio,
    )

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("Done!")
