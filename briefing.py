import requests
from datetime import datetime, timedelta

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

DIV   = "\u2500" * 22
SPACE = ""


def send_telegram(text):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    while text:
        chunk = text[:4000]
        text  = text[4000:]
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })


def get_crypto_prices():
    ids = ",".join(CRYPTO_WATCHLIST.keys())
    url = ("https://api.coingecko.com/api/v3/simple/price?ids=" + ids +
           "&vs_currencies=usd&include_24hr_change=true&include_market_cap=true")
    try:
        return requests.get(url, timeout=10).json()
    except Exception:
        return {}


def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        d = r.json()["data"][0]
        return d["value"], d["value_classification"]
    except Exception:
        return "N/A", "N/A"


def get_btc_dominance():
    try:
        r   = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()
        dom = r["data"]["market_cap_percentage"].get("bitcoin", None)
        return round(dom, 1) if dom else None
    except Exception:
        return None


def get_btc_funding_rate():
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1",
            timeout=10
        ).json()
        return float(r[0]["fundingRate"]) * 100
    except Exception:
        return None


def get_btc_ls_ratio():
    try:
        r = requests.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            "?symbol=BTCUSDT&period=1h&limit=1",
            timeout=10
        ).json()
        return float(r[0]["longShortRatio"])
    except Exception:
        return None


def get_fred_latest(series_id):
    url = ("https://api.stlouisfed.org/fred/series/observations?series_id=" + series_id +
           "&api_key=" + FRED_API_KEY + "&file_type=json&sort_order=desc&limit=2")
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


def get_polymarket_top():
    try:
        r = requests.get(
            "https://clob.polymarket.com/markets?active=true&closed=false", timeout=10
        ).json()
        markets = r if isinstance(r, list) else r.get("data", [])
        mv  = [m for m in markets if m.get("volume") and float(m.get("volume", 0)) > 0]
        top = sorted(mv, key=lambda x: float(x.get("volume", 0)), reverse=True)[:5]
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
        url = ("https://newsapi.org/v2/everything?q=" + query +
               "&language=en&sortBy=publishedAt&pageSize=" + str(page_size) +
               "&apiKey=" + NEWS_API_KEY)
        return requests.get(url, timeout=10).json().get("articles", [])
    except Exception:
        return []


def get_weekly_calendar():
    try:
        r      = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10).json()
        by_day = {}
        for e in r:
            if e.get("country", "").upper() != "USD":
                continue
            impact = e.get("impact", "").lower()
            if impact not in ("high", "medium"):
                continue
            try:
                key = datetime.strptime(e["date"][:10], "%Y-%m-%d").strftime("%a %d %b")
            except Exception:
                continue
            if key not in by_day:
                by_day[key] = []
            fire   = " \U0001f525" if impact == "high" else ""
            detail = ""
            if e.get("forecast"):
                detail += "  Fcst: " + str(e["forecast"])
            if e.get("previous"):
                detail += "  Prev: " + str(e["previous"])
            by_day[key].append(e.get("title", "Unknown") + fire + detail)
        return by_day
    except Exception:
        return {}


def get_groq_analysis(prices, fg_value, fg_label, macro, macro_news, crypto_news,
                      poly, btc_dom, funding_rate, ls_ratio):
    price_lines = []
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d  = prices.get(coin_id, {})
        p  = d.get("usd", "N/A")
        c  = d.get("usd_24h_change", None)
        cs = ("+{:.2f}%".format(c) if c >= 0 else "{:.2f}%".format(c)) if c is not None else "N/A"
        ps = "${:,.2f}".format(p) if isinstance(p, float) else "N/A"
        price_lines.append(symbol + ": " + ps + " (" + cs + ")")

    macro_lines = []
    for label, d in macro.items():
        val  = d["value"]
        date = d["date"]
        prev = d["prev"]
        if val and val != ".":
            try:
                diff = float(val) - float(prev) if prev and prev != "." else 0
                macro_lines.append(label + ": {:.2f} ({:+.2f} vs prev) as of ".format(float(val), diff) + str(date))
            except Exception:
                macro_lines.append(label + ": " + str(val) + " as of " + str(date))

    news_lines   = ["- " + a.get("title","") + " (" + a.get("source",{}).get("name","") + ")"
                    for a in macro_news[:5]]
    crypto_lines = ["- " + a.get("title","") + " (" + a.get("source",{}).get("name","") + ")"
                    for a in crypto_news[:5]]
    poly_lines   = (["- " + m["question"][:80] + " | YES: {:.0f}% | Vol: ${:.1f}M".format(
                        m["yes_prob"], m["volume"]/1e6)
                     for m in poly if m["yes_prob"]] or ["No data"])

    extra = ""
    if btc_dom:
        extra += "BTC Dominance: " + str(btc_dom) + "%\n"
    if funding_rate is not None:
        extra += "BTC Funding Rate: {:.4f}%\n".format(funding_rate)
    if ls_ratio is not None:
        extra += "BTC Long/Short Ratio: {:.2f}\n".format(ls_ratio)

    raw_data = (
        "CRYPTO PRICES (24h):\n" + "\n".join(price_lines) +
        "\n\n" + extra +
        "FEAR & GREED: " + str(fg_value) + " - " + str(fg_label) +
        "\n\nUS MACRO (FRED):\n" + "\n".join(macro_lines) +
        "\n\nMACRO HEADLINES:\n" + "\n".join(news_lines) +
        "\n\nCRYPTO HEADLINES:\n" + "\n".join(crypto_lines) +
        "\n\nPOLYMARKET:\n" + "\n".join(poly_lines)
    )

    prompt = (
        "You are a Lead Macro Analyst reporting directly to Stanley Druckenmiller. "
        "Identify Inflection Points and Asymmetrical Risk/Reward setups. "
        "Markets are reflexive. Narrative drives price until liquidity breaks it.\n\n"
        "RULES:\n"
        "1. Anticipate not React. Tell me what the market is MISPRICING.\n"
        "2. The Fed is the Sun. Filter everything through the Fed Reaction Function.\n"
        "3. The Pig Philosophy. One trade. Risk 1, Reward 5+.\n"
        "4. Brutal and concise. No fluff.\n\n"
        "First write exactly 3 sentiment context bullets:\n"
        "  Geopolitical: [one sentence - geopolitical or macro driver of sentiment]\n"
        "  Technical: [one sentence - price action, liquidations, key level]\n"
        "  Macro Flow: [one sentence - capital rotation visible in data]\n\n"
        "Then write:\n"
        "THEME: [One sentence defining today macro narrative]\n\n"
        "THE NARRATIVE GAP: [Retail/media story vs smart money/bond market reality]\n\n"
        "THE SECOND-ORDER EFFECT: [Biggest story - what does this mean 6-12 months out?]\n\n"
        "THE PIG TRADE: [Highest conviction asymmetric setup. Risk 1, Reward 5. Be specific.]\n\n"
        "TODAY DATA RELEASES TO WATCH: [Key data today and what beat/miss means]\n\n"
        "Raw data:\n" + raw_data + "\n\n"
        "Under 950 words. Think Druckenmiller, not CNBC."
    )

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + GROQ_API_KEY, "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1300,
                "temperature": 0.7,
            },
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "AI analysis unavailable: " + str(e)


def build_message(prices, fg_value, fg_label, macro, poly, calendar,
                  btc_dom, funding_rate, ls_ratio, ai_text):
    now   = datetime.now().strftime("%A, %d %b %Y")
    lines = []

    lines += [
        "\u2600\ufe0f  <b>MORNING BRIEFING</b>",
        "\U0001f4c5  <i>" + now + "  \u00b7  Singapore  \u00b7  6 AM</i>",
        DIV, SPACE,
    ]

    fg_num = int(fg_value) if fg_value != "N/A" else 50
    filled = max(1, round(fg_num / 10))
    bar    = "\u2588" * filled + "\u2591" * (10 - filled)
    if fg_num <= 25:   fg_emoji = "\U0001f534"
    elif fg_num <= 45: fg_emoji = "\U0001f7e0"
    elif fg_num <= 55: fg_emoji = "\U0001f7e1"
    elif fg_num <= 75: fg_emoji = "\U0001f7e2"
    else:              fg_emoji = "\U0001f49a"

    lines.append("\U0001f4ca  <b>SENTIMENT GAUGE</b>")
    lines.append(fg_emoji + "  Index: <b>" + str(fg_value) + " [" + str(fg_label) + "]</b>  " + bar)

    sub = []
    if btc_dom:
        sub.append("BTC Dom: <b>" + str(btc_dom) + "%</b>")
    if funding_rate is not None:
        if abs(funding_rate) < 0.005:
            fr_label = "Neutral"
        elif funding_rate > 0:
            fr_label = "Greed"
        else:
            fr_label = "Fear"
        sub.append("Funding: <b>" + "{:+.4f}".format(funding_rate) + "%</b> <i>(" + fr_label + ")</i>")
    if ls_ratio is not None:
        sub.append("L/S: <b>" + "{:.2f}".format(ls_ratio) + "</b>")
    if sub:
        lines.append("  " + "  \u00b7  ".join(sub))

    sent_bullets = []
    for keyword in ["Geopolitical:", "Technical:", "Macro Flow:"]:
        for line in ai_text.split("\n"):
            if keyword in line:
                sent_bullets.append("  " + line.strip().lstrip("- ").lstrip("* "))
                break
    if sent_bullets:
        lines.append(SPACE)
        lines += sent_bullets
    lines.append(SPACE)

    lines += [DIV, "\U0001f4b0  <b>CRYPTO WATCHLIST</b>", SPACE]
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d      = prices.get(coin_id, {})
        price  = d.get("usd")
        change = d.get("usd_24h_change")
        mcap   = d.get("usd_market_cap")
        ps = "${:,.2f}".format(price) if price else "N/A"
        ms = "  <i>${:.1f}B</i>".format(mcap / 1e9) if mcap else ""
        if change is not None:
            arrow = "\u25b2" if change >= 0 else "\u25bc"
            cs    = arrow + " {:.2f}%".format(abs(change))
        else:
            cs = "\u2014"
        lines.append("  <b>" + symbol + "</b>   " + ps + "   " + cs + ms)
    lines.append(SPACE)

    lines += [DIV, "\U0001f4c9  <b>US MACRO DATA</b>", SPACE]
    new_releases = []
    for label, d in macro.items():
        val  = d["value"]
        date = d["date"]
        prev = d["prev"]
        if val is None or val == ".":
            continue
        try:
            vf  = float(val)
            pf  = float(prev) if prev and prev != "." else None
            vs  = "{:,.2f}".format(vf)
            chg = ""
            if pf is not None:
                diff  = vf - pf
                arrow = "\u25b2" if diff > 0 else "\u25bc" if diff < 0 else "\u2192"
                chg   = "  " + arrow + " <i>{:+.2f}</i>".format(diff)
        except Exception:
            vs  = str(val)
            chg = ""
        fresh = "\U0001f195 " if was_released_today(date) else ""
        if was_released_today(date):
            new_releases.append(label)
        lines.append("  " + fresh + "<b>" + label + "</b>:  " + vs + chg + "  <i>(" + str(date) + ")</i>")

    lines.append(SPACE)
    if new_releases:
        lines.append("\U0001f6a8  <b>Released today:</b> " + ", ".join(new_releases))
    else:
        lines.append("\u23f0  <i>No new US data releases today</i>")
    lines.append(SPACE)

    lines += [DIV, "\U0001f4c5  <b>ECONOMIC DOCKET \u2014 THIS WEEK</b>", SPACE]
    if calendar:
        for day, events in calendar.items():
            lines.append("  <b>" + day + "</b>")
            for ev in events[:4]:
                lines.append("    \u2023 " + ev)
            lines.append(SPACE)
    else:
        lines += ["  <i>Calendar unavailable</i>", SPACE]

    lines += [DIV, "\U0001f3af  <b>POLYMARKET \u2014 TOP BY VOLUME</b>", SPACE]
    if poly:
        for m in poly:
            vol = "${:.1f}M".format(m["volume"] / 1e6) if m["volume"] >= 1e6 else "${:,.0f}".format(m["volume"])
            yes = "  <b>YES {:.0f}%</b>".format(m["yes_prob"]) if m["yes_prob"] else ""
            lines.append("  \u2022 " + m["question"][:75] + yes + "  <i>" + vol + "</i>")
    else:
        lines.append("  <i>Could not load Polymarket data</i>")
    lines.append(SPACE)

    lines += [DIV, "\U0001f9e0  <b>DRUCKENMILLER ANALYSIS</b>", SPACE]
    clean_ai = []
    skip = False
    for line in ai_text.split("\n"):
        if any(k in line for k in ["Geopolitical:", "Technical:", "Macro Flow:"]):
            skip = True
        if line.strip().startswith("THEME:"):
            skip = False
        if not skip:
            clean_ai.append(line)
    lines.append("\n".join(clean_ai).strip())
    lines.append(SPACE)

    lines += [
        DIV,
        "\U0001f916  <i>CoinGecko \u00b7 Binance \u00b7 FRED \u00b7 Polymarket \u00b7 Groq AI</i>"
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching data...")
    prices             = get_crypto_prices()
    fg_value, fg_label = get_fear_greed()
    macro              = get_all_macro()
    poly               = get_polymarket_top()
    macro_news         = get_news("Federal Reserve OR CPI OR inflation OR GDP OR recession OR FOMC OR ISM PMI", 5)
    crypto_news        = get_news("bitcoin OR ethereum OR crypto OR DeFi OR polymarket OR hyperliquid", 5)
    calendar           = get_weekly_calendar()
    btc_dom            = get_btc_dominance()
    funding_rate       = get_btc_funding_rate()
    ls_ratio           = get_btc_ls_ratio()

    print("Running AI analysis...")
    ai_text = get_groq_analysis(
        prices, fg_value, fg_label, macro,
        macro_news, crypto_news, poly,
        btc_dom, funding_rate, ls_ratio
    )

    print("Building message...")
    full_message = build_message(
        prices, fg_value, fg_label, macro, poly, calendar,
        btc_dom, funding_rate, ls_ratio, ai_text
    )

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("Done!")
