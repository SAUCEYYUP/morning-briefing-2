import requests
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = "8734149271:AAHM5T5diwscMnfk7gzGkiRsP-uRbURVcjs"
TELEGRAM_CHAT_ID   = "623392672"
NEWS_API_KEY       = "425b2c8e51244bb9a09880eec07d56fb"
FRED_API_KEY       = "bea607ec27e9abfbb37124f5013e115e"
GROQ_API_KEY       = "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"
FMP_API_KEY        = "0hO9aKx9HzPzsMALWMjHmfoYr67HkK2n"

CRYPTO_WATCHLIST = {
    "bitcoin":      "BTC",
    "ethereum":     "ETH",
    "solana":       "SOL",
    "hyperliquid":  "HYPE",
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

DIVIDER = "\u2500" * 22
SPACER  = ""


def send_telegram(text):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    while text:
        chunk = text[:4000]
        text = text[4000:]
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
        r = requests.get("https://clob.polymarket.com/markets?active=true&closed=false", timeout=10).json()
        markets = r if isinstance(r, list) else r.get("data", [])
        markets_with_vol = [m for m in markets if m.get("volume") and float(m.get("volume", 0)) > 0]
        top = sorted(markets_with_vol, key=lambda x: float(x.get("volume", 0)), reverse=True)[:5]
        results = []
        for m in top:
            yes_price = None
            for t in m.get("tokens", []):
                if t.get("outcome", "").upper() == "YES":
                    yes_price = float(t.get("price", 0)) * 100
            results.append({
                "question": m.get("question", "Unknown"),
                "volume": float(m.get("volume", 0)),
                "yes_prob": yes_price,
            })
        return results
    except Exception:
        return []


def get_news(query, page_size=4):
    try:
        url = ("https://newsapi.org/v2/everything?q=" + query +
               "&language=en&sortBy=publishedAt&pageSize=" + str(page_size) +
               "&apiKey=" + NEWS_API_KEY)
        return requests.get(url, timeout=10).json().get("articles", [])
    except Exception:
        return []


def get_weekly_calendar():
    today = datetime.now()
    end   = today + timedelta(days=7)
    url   = ("https://financialmodelingprep.com/api/v3/economic_calendar"
             "?from=" + today.strftime("%Y-%m-%d") +
             "&to=" + end.strftime("%Y-%m-%d") +
             "&apikey=" + FMP_API_KEY)
    try:
        events = requests.get(url, timeout=10).json()
        filtered = [
            e for e in events
            if e.get("country", "").upper() == "US"
            and e.get("impact", "").lower() in ("high", "medium")
        ]
        by_day = {}
        for e in filtered:
            date_raw = e.get("date", "")[:10]
            try:
                d   = datetime.strptime(date_raw, "%Y-%m-%d")
                key = d.strftime("%a %d %b")
            except Exception:
                key = date_raw
            if key not in by_day:
                by_day[key] = []
            name     = e.get("event", "Unknown")
            forecast = e.get("estimate", None)
            previous = e.get("previous", None)
            impact   = e.get("impact", "").lower()
            fire     = " \U0001f525" if impact == "high" else ""
            detail   = ""
            if forecast is not None:
                detail += "  Fcst: " + str(forecast)
            if previous is not None:
                detail += "  Prev: " + str(previous)
            by_day[key].append(name + fire + detail)
        return by_day
    except Exception:
        return {}


def get_groq_analysis(prices, fg_value, fg_label, macro, macro_headlines, crypto_headlines, poly):
    price_lines = []
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d = prices.get(coin_id, {})
        p = d.get("usd", "N/A")
        c = d.get("usd_24h_change", None)
        change_str = ("+{:.2f}%".format(c) if c >= 0 else "{:.2f}%".format(c)) if c is not None else "N/A"
        price_str = "${:,.2f}".format(p) if isinstance(p, float) else "N/A"
        price_lines.append(symbol + ": " + price_str + " (" + change_str + ")")

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

    news_lines = []
    for a in macro_headlines[:5]:
        news_lines.append("- " + a.get("title", "") + " (" + a.get("source", {}).get("name", "") + ")")

    crypto_lines = []
    for a in crypto_headlines[:5]:
        crypto_lines.append("- " + a.get("title", "") + " (" + a.get("source", {}).get("name", "") + ")")

    poly_lines = []
    if poly:
        for m in poly:
            if m["yes_prob"]:
                poly_lines.append("- " + m["question"][:80] + " | YES: {:.0f}% | Vol: ${:.1f}M".format(m["yes_prob"], m["volume"] / 1e6))
    if not poly_lines:
        poly_lines = ["No data"]

    raw_data = (
        "CRYPTO PRICES (24h):\n" + "\n".join(price_lines) +
        "\n\nFEAR & GREED INDEX: " + str(fg_value) + " - " + str(fg_label) +
        "\n\nUS MACRO DATA (FRED):\n" + "\n".join(macro_lines) +
        "\n\nTOP MACRO HEADLINES:\n" + "\n".join(news_lines) +
        "\n\nTOP CRYPTO HEADLINES:\n" + "\n".join(crypto_lines) +
        "\n\nPOLYMARKET TOP MARKETS:\n" + "\n".join(poly_lines)
    )

    prompt = (
        "You are a Lead Macro Analyst reporting directly to Stanley Druckenmiller. "
        "Your goal is not to report news but to identify Inflection Points and Asymmetrical Risk/Reward setups. "
        "Markets are reflexive. Narrative drives price until liquidity breaks it.\n\n"
        "RULES:\n"
        "1. Anticipate, do not React. Tell me what the market is MISPRICING, not what happened.\n"
        "2. The Fed is the Sun. Filter every event through how it affects the Fed Reaction Function and global liquidity.\n"
        "3. The Pig Philosophy. Identify the ONE trade with highest conviction where risk=1, reward=5+.\n"
        "4. Be brutal and concise. No fluff. Every sentence must have edge.\n\n"
        "OUTPUT FORMAT (use these exact headers):\n"
        "THEME: [One sentence defining today macro narrative]\n\n"
        "STRATEGIC SENTIMENT: [2-3 sentences using Fear and Greed as CONTRARIAN signal]\n\n"
        "THE LIQUIDITY BOARD:\n"
        "Asset | Price | 24h | Macro Implication\n"
        "[fill for BTC, Gold, Oil, DXY, 10Y Yield - estimate if not in data]\n\n"
        "THE NARRATIVE GAP: [Where retail/media story differs from smart money/bond market reality]\n\n"
        "THE SECOND-ORDER EFFECT: [For biggest story today, what does this mean 6-12 months out?]\n\n"
        "THE PIG TRADE: [Single highest conviction asymmetric setup. Risk 1, Reward 5. Be specific.]\n\n"
        "TODAY DATA RELEASES TO WATCH: [Any macro data dropping today and what a beat/miss means]\n\n"
        "Raw data:\n" + raw_data + "\n\n"
        "Keep total response under 900 words. Think Druckenmiller, not CNBC."
    )

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
                "temperature": 0.7,
            },
            timeout=30,
        )
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return "AI analysis unavailable: " + str(e)


def build_message(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news, calendar):
    now   = datetime.now().strftime("%A, %d %b %Y")
    lines = []

    # HEADER
    lines.append("\u2600\ufe0f  <b>MORNING BRIEFING</b>")
    lines.append("\U0001f4c5  <i>" + now + " \u00b7 Singapore</i>")
    lines.append(DIVIDER)
    lines.append(SPACER)

    # SENTIMENT
    fg_num = int(fg_value) if fg_value != "N/A" else 50
    if fg_num <= 25:
        fg_emoji = "\U0001f534"
        fg_bar   = "\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591"
    elif fg_num <= 45:
        fg_emoji = "\U0001f7e0"
        fg_bar   = "\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2591"
    elif fg_num <= 55:
        fg_emoji = "\U0001f7e1"
        fg_bar   = "\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591"
    elif fg_num <= 75:
        fg_emoji = "\U0001f7e2"
        fg_bar   = "\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591"
    else:
        fg_emoji = "\U0001f49a"
        fg_bar   = "\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591"

    lines.append("\U0001f9e0  <b>MARKET SENTIMENT</b>")
    lines.append(fg_emoji + "  <b>" + str(fg_value) + " \u2014 " + str(fg_label) + "</b>  " + fg_bar)
    lines.append(SPACER)

    # CRYPTO
    lines.append(DIVIDER)
    lines.append("\U0001f4b0  <b>CRYPTO WATCHLIST</b>")
    lines.append(SPACER)
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d      = prices.get(coin_id, {})
        price  = d.get("usd")
        change = d.get("usd_24h_change")
        mcap   = d.get("usd_market_cap")
        price_str = "${:,.2f}".format(price) if price else "N/A"
        mcap_str  = "  <i>MCap ${:.1f}B</i>".format(mcap / 1e9) if mcap else ""
        if change is not None:
            arrow      = "\u25b2" if change >= 0 else "\u25bc"
            change_str = arrow + " {:.2f}%".format(abs(change))
        else:
            change_str = "\u2014"
        lines.append("  <b>" + symbol + "</b>   " + price_str + "   " + change_str + mcap_str)
    lines.append(SPACER)

    # MACRO DATA
    lines.append(DIVIDER)
    lines.append("\U0001f4ca  <b>US MACRO DATA</b>")
    lines.append(SPACER)
    new_releases = []
    for label, d in macro.items():
        val  = d["value"]
        date = d["date"]
        prev = d["prev"]
        if val is None or val == ".":
            continue
        try:
            val_f  = float(val)
            prev_f = float(prev) if prev and prev != "." else None
            val_str = "{:,.2f}".format(val_f)
            if prev_f is not None:
                diff  = val_f - prev_f
                arrow = "\u25b2" if diff > 0 else "\u25bc" if diff < 0 else "\u2192"
                chg   = "  " + arrow + " <i>{:+.2f}</i>".format(diff)
            else:
                chg = ""
        except Exception:
            val_str = str(val)
            chg = ""
        fresh = "\U0001f195 " if was_released_today(date) else ""
        if was_released_today(date):
            new_releases.append(label)
        lines.append("  " + fresh + "<b>" + label + "</b>:  " + val_str + chg + "  <i>(" + str(date) + ")</i>")

    lines.append(SPACER)
    if new_releases:
        lines.append("\U0001f6a8  <b>Released today:</b> " + ", ".join(new_releases))
    else:
        lines.append("\u23f0  <i>No new US data releases today</i>")
    lines.append(SPACER)

    # WEEKLY CALENDAR
    lines.append(DIVIDER)
    lines.append("\U0001f4c5  <b>ECONOMIC DOCKET \u2014 THIS WEEK</b>")
    lines.append(SPACER)
    if calendar:
        for day, events in calendar.items():
            lines.append("  <b>" + day + "</b>")
            for ev in events[:4]:
                lines.append("    \u2023 " + ev)
            lines.append(SPACER)
    else:
        lines.append("  <i>Calendar unavailable</i>")
        lines.append(SPACER)

    # POLYMARKET
    lines.append(DIVIDER)
    lines.append("\U0001f3af  <b>POLYMARKET \u2014 TOP BY VOLUME</b>")
    lines.append(SPACER)
    if poly:
        for m in poly:
            vol = "${:.1f}M".format(m["volume"] / 1e6) if m["volume"] >= 1e6 else "${:,.0f}".format(m["volume"])
            yes = "  <b>YES {:.0f}%</b>".format(m["yes_prob"]) if m["yes_prob"] else ""
            lines.append("  \u2022 " + m["question"][:75] + yes + "  <i>" + vol + "</i>")
    else:
        lines.append("  <i>Could not load Polymarket data</i>")
    lines.append(SPACER)

    # MACRO NEWS
    lines.append(DIVIDER)
    lines.append("\U0001f30d  <b>MACRO HEADLINES</b>")
    lines.append(SPACER)
    for a in macro_news:
        title  = a.get("title", "")[:85]
        url    = a.get("url", "")
        source = a.get("source", {}).get("name", "")
        lines.append('  \u2022 <a href="' + url + '">' + title + '</a>')
        lines.append("    <i>" + source + "</i>")
        lines.append(SPACER)

    # CRYPTO NEWS
    lines.append(DIVIDER)
    lines.append("\u20bf  <b>CRYPTO HEADLINES</b>")
    lines.append(SPACER)
    for a in crypto_news:
        title  = a.get("title", "")[:85]
        url    = a.get("url", "")
        source = a.get("source", {}).get("name", "")
        lines.append('  \u2022 <a href="' + url + '">' + title + '</a>')
        lines.append("    <i>" + source + "</i>")
        lines.append(SPACER)

    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching data...")
    prices      = get_crypto_prices()
    fg_value, fg_label = get_fear_greed()
    macro       = get_all_macro()
    poly        = get_polymarket_top()
    macro_news  = get_news("Federal Reserve OR CPI OR inflation OR GDP OR recession OR FOMC OR ISM PMI", 4)
    crypto_news = get_news("bitcoin OR ethereum OR crypto OR DeFi OR polymarket OR hyperliquid", 4)
    calendar    = get_weekly_calendar()

    print("Building message...")
    raw_msg = build_message(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news, calendar)

    print("Running AI analysis...")
    ai_analysis = get_groq_analysis(prices, fg_value, fg_label, macro, macro_news, crypto_news, poly)

    ai_header = ("\n" + DIVIDER + "\n"
                 "\U0001f9e0  <b>DRUCKENMILLER ANALYSIS</b>\n" +
                 DIVIDER + "\n\n")
    footer = ("\n" + DIVIDER + "\n"
              "\U0001f916  <i>CoinGecko \u00b7 FRED \u00b7 FMP \u00b7 Polymarket \u00b7 NewsAPI \u00b7 Groq AI</i>")

    full_message = raw_msg + ai_header + ai_analysis + footer

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("Done!")
