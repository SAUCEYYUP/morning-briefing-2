import json
import requests
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = "8734149271:AAHM5T5diwscMnfk7gzGkiRsP-uRbURVcjs"
TELEGRAM_CHAT_ID    = "623392672"
THESIS_CHANNEL_ID   = "-1003787201269"   # private channel — bot is admin
NEWS_API_KEY        = "425b2c8e51244bb9a09880eec07d56fb"
FRED_API_KEY        = "bea607ec27e9abfbb37124f5013e115e"
GROQ_API_KEY        = "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"

CRYPTO_WATCHLIST = {
    "bitcoin":     "BTC",
    "ethereum":    "ETH",
    "solana":      "SOL",
    "hyperliquid": "HYPE",
}

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

MARKET_TICKERS = {
    "^GSPC":    ("S&P 500", ""),
    "^IXIC":    ("Nasdaq",  ""),
    "^VIX":     ("VIX",     ""),
    "DX-Y.NYB": ("DXY",    ""),
    "GC=F":     ("Gold",    "$/oz"),
    "CL=F":     ("WTI Oil", "$/bbl"),
    "^TNX":     ("US 10Y",  "%"),
}

DIVIDER = "─" * 26


# ══════════════════════════════════════════════════════════════════════════════
# THESIS STORE  —  Telegram private channel as database
# The pinned message in THESIS_CHANNEL_ID holds a JSON blob.
# Monday  → generate fresh thesis, post + pin new message.
# Tue–Fri → read pinned message, score today, edit message in-place.
# ══════════════════════════════════════════════════════════════════════════════

def _tg(method, **kwargs):
    """Raw Telegram API call. Returns response JSON."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, json=kwargs, timeout=15)
        return r.json()
    except Exception as e:
        print(f"[TG ERROR] {method}: {e}")
        return {}


def thesis_load():
    """
    Read the pinned message from the thesis channel.
    Returns (message_id, thesis_dict) or (None, None) if nothing pinned.
    """
    info = _tg("getChat", chat_id=THESIS_CHANNEL_ID)
    pinned = info.get("result", {}).get("pinned_message")
    if not pinned:
        return None, None
    try:
        text  = pinned.get("text", "")
        # JSON is stored between sentinel markers so other text can coexist
        start = text.index("<<<THESIS_JSON>>>") + len("<<<THESIS_JSON>>>")
        end   = text.index("<<<END_THESIS>>>")
        data  = json.loads(text[start:end].strip())
        return pinned["message_id"], data
    except Exception:
        return pinned.get("message_id"), None


def thesis_save(message_id, data):
    """
    Persist thesis dict.
    If message_id is None → post a new message and pin it.
    Otherwise → edit the existing pinned message in-place.
    """
    blob = f"<<<THESIS_JSON>>>\n{json.dumps(data, indent=2)}\n<<<END_THESIS>>>"
    if message_id is None:
        # First ever post — send then pin
        resp = _tg("sendMessage", chat_id=THESIS_CHANNEL_ID, text=blob)
        mid  = resp.get("result", {}).get("message_id")
        if mid:
            _tg("pinChatMessage", chat_id=THESIS_CHANNEL_ID,
                message_id=mid, disable_notification=True)
        return mid
    else:
        _tg("editMessageText", chat_id=THESIS_CHANNEL_ID,
            message_id=message_id, text=blob)
        return message_id


def is_monday():
    return datetime.now().weekday() == 0   # 0 = Monday


def week_of_monday():
    """ISO date string of this week's Monday."""
    today = datetime.now().date()
    return str(today - timedelta(days=today.weekday()))


def day_number_in_week():
    """1 = Monday … 5 = Friday."""
    return datetime.now().weekday() + 1


# ── AI: generate Monday thesis ─────────────────────────────────────────────
def generate_weekly_thesis(raw_data_str):
    prompt = f"""You are a Lead Macro Analyst at a global macro hedge fund.
It is Monday morning. Generate this week's macro thesis.

Output EXACTLY this JSON and nothing else — no preamble, no markdown fences:
{{
  "thesis": "<2-3 sentence directional macro view for the week>",
  "conviction_direction": "<BULLISH|NEUTRAL|BEARISH>",
  "conviction_score": <integer 1-10>,
  "key_variables": [
    "<specific measurable thing that will CONFIRM the thesis>",
    "<specific measurable thing that will CONFIRM the thesis>",
    "<specific measurable thing that will CHALLENGE the thesis>"
  ],
  "invalidation": "<single sentence: the one event or print that kills this thesis entirely>"
}}

Raw market data:
{raw_data_str}

Be specific. Use actual prices and levels from the data. Think Druckenmiller."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model":       "llama-3.3-70b-versatile",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  600,
                "temperature": 0.3,
            },
            timeout=30,
        )
        text = r.json()["choices"][0]["message"]["content"].strip()
        # Strip accidental markdown fences
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[THESIS GEN ERROR] {e}")
        return None


# ── AI: score today against thesis ────────────────────────────────────────
def score_today_vs_thesis(thesis_data, raw_data_str, today_events):
    today_str = datetime.now().strftime("%A %d %b")
    calendar_note = (
        "Today's scheduled data: " + ", ".join(today_events)
        if today_events else "No major data scheduled today."
    )

    prompt = f"""You are a Lead Macro Analyst scoring today's data against Monday's weekly thesis.

MONDAY'S THESIS:
\"{thesis_data['thesis']}\"
Direction: {thesis_data['conviction_direction']}  {thesis_data['conviction_score']}/10
Key variables:
{chr(10).join(f"- {v}" for v in thesis_data['key_variables'])}
Invalidation trigger: {thesis_data['invalidation']}

Today is {today_str}. {calendar_note}

Today's raw market data:
{raw_data_str}

Output EXACTLY this JSON and nothing else — no preamble, no markdown fences:
{{
  "status": "<CONFIRMS|CHALLENGED|INVALIDATED>",
  "note": "<1-2 sharp sentences: what today's data did to the thesis>",
  "variables_status": [
    "<✅ HOLDING | ⚠️ AT RISK | ❌ BROKEN>: <variable 1 text>",
    "<✅ HOLDING | ⚠️ AT RISK | ❌ BROKEN>: <variable 2 text>",
    "<✅ HOLDING | ⚠️ AT RISK | ❌ BROKEN>: <variable 3 text>"
  ]
}}

Be blunt. Reference actual prices. No filler."""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model":       "llama-3.3-70b-versatile",
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  400,
                "temperature": 0.25,
            },
            timeout=30,
        )
        text = r.json()["choices"][0]["message"]["content"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[THESIS SCORE ERROR] {e}")
        return None


# ── Orchestrator: run thesis logic, return display block ──────────────────
def run_thesis_tracker(raw_data_str, today_events):
    """
    Main entry point for the thesis tracker.
    Returns (thesis_data, today_score, display_block_lines).
    """
    msg_id, thesis_data = thesis_load()
    today_str   = datetime.now().strftime("%Y-%m-%d")
    day_num     = day_number_in_week()
    week_monday = week_of_monday()

    # ── Monday: always generate a fresh thesis ─────────────────────────────
    if is_monday() or thesis_data is None or thesis_data.get("week_of") != week_monday:
        print("Generating new weekly thesis (Monday)...")
        new_thesis = generate_weekly_thesis(raw_data_str)
        if new_thesis is None:
            return None, None, ["  <i>Thesis generation failed — will retry tomorrow.</i>"]

        thesis_data = {
            "week_of":              week_monday,
            "thesis":               new_thesis["thesis"],
            "conviction_direction": new_thesis["conviction_direction"],
            "conviction_score":     new_thesis["conviction_score"],
            "key_variables":        new_thesis["key_variables"],
            "invalidation":         new_thesis["invalidation"],
            "daily_scores":         [],   # will be populated Tue–Fri
        }
        # Score Monday itself
        today_score = score_today_vs_thesis(thesis_data, raw_data_str, today_events)
        if today_score:
            today_score["date"] = today_str
            thesis_data["daily_scores"].append(today_score)

        thesis_save(msg_id, thesis_data)

    # ── Tue–Fri: score today if not already scored ─────────────────────────
    else:
        already_scored = any(d.get("date") == today_str for d in thesis_data.get("daily_scores", []))
        if already_scored:
            # Carry forward — mark the gap if previous day is missing
            today_score = next(
                (d for d in thesis_data["daily_scores"] if d["date"] == today_str), None
            )
        else:
            print("Scoring today vs weekly thesis...")
            # Check if yesterday was scored; if not, note the gap
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            gap_note  = ""
            if not any(d.get("date") == yesterday for d in thesis_data.get("daily_scores", [])):
                gap_note = " [Gap: previous day not scored — carrying forward.]"

            today_score = score_today_vs_thesis(thesis_data, raw_data_str, today_events)
            if today_score:
                today_score["date"]     = today_str
                today_score["gap_note"] = gap_note
                thesis_data["daily_scores"].append(today_score)
                thesis_save(msg_id, thesis_data)

    # ── Build display block ────────────────────────────────────────────────
    lines = _build_thesis_block(thesis_data, today_score, day_num)
    return thesis_data, today_score, lines


def _build_thesis_block(thesis_data, today_score, day_num):
    lines = []

    direction = thesis_data.get("conviction_direction", "NEUTRAL")
    score     = thesis_data.get("conviction_score", 5)
    dir_emoji = {"BULLISH": "🟢", "NEUTRAL": "🟡", "BEARISH": "🔴"}.get(direction, "⚪")

    # Score bar  e.g. ▓▓▓▓▓▓░░░░  6/10
    filled  = max(1, score)
    bar     = "▓" * filled + "░" * (10 - filled)

    # Running tally from daily_scores
    scores_list = thesis_data.get("daily_scores", [])
    confirms    = sum(1 for d in scores_list if d.get("status") == "CONFIRMS")
    challenged  = sum(1 for d in scores_list if d.get("status") == "CHALLENGED")
    invalidated = sum(1 for d in scores_list if d.get("status") == "INVALIDATED")

    lines += [
        DIVIDER,
        f"📋  <b>WEEKLY THESIS</b>  —  Day {day_num}/5",
        "",
        f"{dir_emoji}  <b>{direction}</b>  {score}/10   {bar}",
        "",
        f"<i>{thesis_data.get('thesis', 'No thesis available.')}</i>",
        "",
        "<b>Key Variables:</b>",
    ]

    # Variable statuses — use today's score if available, else raw variables
    if today_score and today_score.get("variables_status"):
        for vs in today_score["variables_status"]:
            lines.append(f"  {vs}")
    else:
        for v in thesis_data.get("key_variables", []):
            lines.append(f"  ⬜ {v}")

    lines += [
        "",
        f"<b>Invalidation trigger:</b>  <i>{thesis_data.get('invalidation', '—')}</i>",
        "",
    ]

    # Today's score
    if today_score:
        status     = today_score.get("status", "—")
        note       = today_score.get("note", "")
        gap        = today_score.get("gap_note", "")
        status_map = {"CONFIRMS": "✅ CONFIRMS", "CHALLENGED": "⚠️ CHALLENGED", "INVALIDATED": "❌ INVALIDATED"}
        status_str = status_map.get(status, status)
        lines += [
            f"<b>Today:</b>  {status_str}",
            f"<i>{note}</i>",
        ]
        if gap:
            lines.append(f"<i>{gap}</i>")
    else:
        lines.append("<b>Today:</b>  <i>Scoring unavailable</i>")

    lines += [
        "",
        f"<b>Week:</b>  ✅ {confirms} confirms  ·  ⚠️ {challenged} challenged  ·  ❌ {invalidated} invalidated",
    ]

    return lines


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# MARKET DATA
# ══════════════════════════════════════════════════════════════════════════════

def get_market_snapshot():
    results = {}
    for ticker, (label, unit) in MARKET_TICKERS.items():
        try:
            url    = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
            r      = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).json()
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
    results = {}
    for symbol, label in OI_SYMBOLS.items():
        try:
            oi_now = float(
                requests.get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}", timeout=10)
                .json()["openInterest"]
            )
            hist = requests.get(
                f"https://fapi.binance.com/futures/data/openInterestHist"
                f"?symbol={symbol}&period=1h&limit=2",
                timeout=10,
            ).json()
            chg_pct = None
            if len(hist) >= 2:
                oi_prev   = float(hist[0]["sumOpenInterest"])
                oi_curr_h = float(hist[1]["sumOpenInterest"])
                chg_pct   = ((oi_curr_h - oi_prev) / oi_prev) * 100 if oi_prev else None

            mark   = float(
                requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}", timeout=10)
                .json()["markPrice"]
            )
            results[label] = {"oi_usd": oi_now * mark, "oi_change_pct": chg_pct}
        except Exception:
            pass
    return results


# ══════════════════════════════════════════════════════════════════════════════
# MACRO / CALENDAR / NEWS / POLYMARKET
# ══════════════════════════════════════════════════════════════════════════════

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
    return {
        label: dict(zip(("value", "date", "prev"), get_fred_latest(sid)))
        for sid, label in FRED_SERIES.items()
    }


def was_released_today(date_str):
    if not date_str:
        return False
    try:
        return (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days <= 1
    except Exception:
        return False


def get_weekly_calendar():
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
            by_day.setdefault(day_key, []).append(e.get("title", "Unknown") + badge + detail)
            if event_date == today_str:
                today_ev.append(e.get("title", "Unknown") + detail)
        return by_day, today_ev
    except Exception:
        return {}, []


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


def get_news(query, page_size=5):
    try:
        url = (
            f"https://newsapi.org/v2/everything?q={query}"
            f"&language=en&sortBy=publishedAt&pageSize={page_size}&apiKey={NEWS_API_KEY}"
        )
        return requests.get(url, timeout=10).json().get("articles", [])
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# DAILY AI ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def build_raw_data_str(prices, fg_value, fg_label, macro, macro_news, crypto_news,
                       poly, btc_dom, funding_rate, ls_ratio, markets, oi_data,
                       eth_btc_ratio, today_events):
    """Assemble the raw data string used by both the thesis AI and the daily analysis AI."""
    price_lines = []
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d  = prices.get(coin_id, {})
        p  = d.get("usd")
        c  = d.get("usd_24h_change")
        price_lines.append(
            f"{symbol}: {'$'+f'{p:,.2f}' if p else 'N/A'} "
            f"({'N/A' if c is None else f'{c:+.2f}%'})"
        )
    if eth_btc_ratio:
        price_lines.append(f"ETH/BTC Ratio: {eth_btc_ratio:.5f}")

    market_lines = [
        f"{lbl}: {d['price']:,.2f} ({d['change_pct']:+.2f}%)" if d["change_pct"] is not None
        else f"{lbl}: {d['price']:,.2f}"
        for lbl, d in markets.items()
    ]

    oi_lines = [
        f"{lbl} OI: ${d['oi_usd']/1e9:.2f}B "
        f"(1h chg: {d['oi_change_pct']:+.2f}%)" if d["oi_change_pct"] is not None
        else f"{lbl} OI: ${d['oi_usd']/1e9:.2f}B"
        for lbl, d in oi_data.items()
    ]

    macro_lines = []
    for label, d in macro.items():
        val, date, prev = d["value"], d["date"], d["prev"]
        if val and val != ".":
            try:
                diff = float(val) - float(prev) if prev and prev != "." else 0
                macro_lines.append(f"{label}: {float(val):.2f} ({diff:+.2f} vs prev) as of {date}")
            except Exception:
                macro_lines.append(f"{label}: {val} as of {date}")

    extra_parts = []
    if btc_dom      is not None: extra_parts.append(f"BTC Dominance: {btc_dom}%")
    if funding_rate is not None: extra_parts.append(f"BTC Funding Rate: {funding_rate:.4f}%")
    if ls_ratio     is not None: extra_parts.append(f"BTC Long/Short Ratio: {ls_ratio:.2f}")

    news_lines   = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})" for a in macro_news[:5]]
    crypto_lines = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})" for a in crypto_news[:5]]
    poly_lines   = [
        f"- {m['question'][:80]} | YES: {m['yes_prob']:.0f}% | Vol: ${m['volume']/1e6:.1f}M"
        for m in poly if m["yes_prob"]
    ] or ["No data"]

    today_block = (
        "TODAY'S SCHEDULED US DATA RELEASES:\n" + "\n".join(f"- {e}" for e in today_events)
        if today_events else
        "TODAY'S SCHEDULED US DATA RELEASES: None scheduled today."
    )

    return "\n\n".join(filter(None, [
        "CRYPTO PRICES (24h):\n"  + "\n".join(price_lines),
        "GLOBAL MARKETS:\n"        + "\n".join(market_lines),
        "OPEN INTEREST:\n"         + "\n".join(oi_lines) if oi_lines else "",
        "\n".join(extra_parts)     if extra_parts else "",
        f"FEAR & GREED: {fg_value} - {fg_label}",
        "US MACRO (FRED):\n"       + "\n".join(macro_lines),
        "MACRO HEADLINES:\n"       + "\n".join(news_lines),
        "CRYPTO HEADLINES:\n"      + "\n".join(crypto_lines),
        "POLYMARKET:\n"            + "\n".join(poly_lines),
        today_block,
    ]))


def get_groq_analysis(raw_data_str, today_events, thesis_data, today_score):
    # Inject thesis context so daily analysis stays aligned with the weekly view
    thesis_context = ""
    if thesis_data:
        thesis_context = f"""
WEEKLY THESIS CONTEXT (set Monday):
Direction: {thesis_data['conviction_direction']}  {thesis_data['conviction_score']}/10
Thesis: {thesis_data['thesis']}
Today's thesis status: {today_score.get('status', 'N/A') if today_score else 'N/A'}
"""

    today_block = (
        "TODAY'S SCHEDULED US DATA RELEASES:\n" + "\n".join(f"- {e}" for e in today_events)
        if today_events else
        "TODAY'S SCHEDULED US DATA RELEASES: None scheduled today."
    )

    prompt = f"""You are a Lead Macro Analyst reporting directly to Stanley Druckenmiller.
{thesis_context}
CRITICAL RULES:
1. For "TODAY DATA RELEASES TO WATCH" — reference ONLY events listed under \
"TODAY'S SCHEDULED US DATA RELEASES". If none, say so. Never invent from memory.
2. KEY LEVELS must be anchored to actual prices in the data. Round to clean levels. Never fabricate.
3. Every sentence must earn its place. No filler.

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

TODAY DATA RELEASES TO WATCH: [ONLY from calendar data. If none, say so clearly.]

Raw data:
{raw_data_str}

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


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_message(prices, fg_value, fg_label, macro, poly, calendar,
                  btc_dom, funding_rate, ls_ratio, ai_text,
                  markets, oi_data, eth_btc_ratio, thesis_block_lines):
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

    # AI situational awareness bullets
    sent_bullets = []
    for keyword in ("Geopolitical:", "Technical:", "Macro Flow:"):
        for line in ai_text.split("\n"):
            if keyword in line:
                sent_bullets.append("  " + line.strip().lstrip("- *"))
                break
    if sent_bullets:
        lines += [""] + sent_bullets
    lines.append("")

    # ── Weekly Thesis Tracker ─────────────────────────────────────────────────
    lines += thesis_block_lines
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


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Fetching market data...")
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

    # Build shared raw data string (used by both thesis AI and daily AI)
    raw_data_str = build_raw_data_str(
        prices, fg_value, fg_label, macro, macro_news, crypto_news,
        poly, btc_dom, funding_rate, ls_ratio, markets, oi_data,
        eth_btc_ratio, today_ev,
    )

    # Run thesis tracker (Monday = generate, Tue–Fri = score)
    print("Running thesis tracker...")
    thesis_data, today_score, thesis_block = run_thesis_tracker(raw_data_str, today_ev)

    # Daily Druckenmiller analysis (thesis-aware)
    print("Running daily AI analysis...")
    ai_text = get_groq_analysis(raw_data_str, today_ev, thesis_data, today_score)

    print("Building message...")
    full_message = build_message(
        prices, fg_value, fg_label, macro, poly, calendar,
        btc_dom, funding_rate, ls_ratio, ai_text,
        markets, oi_data, eth_btc_ratio,
        thesis_block,
    )

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("Done!")
