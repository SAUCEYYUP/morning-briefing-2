import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = "8734149271:AAHM5T5diwscMnfk7gzGkiRsP-uRbURVcjs"
TELEGRAM_CHAT_ID   = "623392672"
NEWS_API_KEY       = "425b2c8e51244bb9a09880eec07d56fb"
FRED_API_KEY       = "bea607ec27e9abfbb37124f5013e115e"
GROQ_API_KEY       = "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"

CRYPTO_WATCHLIST = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "chainlink": "LINK",
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


def get_news(query, page_size=5):
    try:
        url = ("https://newsapi.org/v2/everything?q=" + query +
               "&language=en&sortBy=publishedAt&pageSize=" + str(page_size) +
               "&apiKey=" + NEWS_API_KEY)
        return requests.get(url, timeout=10).json().get("articles", [])
    except Exception:
        return []


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
        val = d["value"]
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


def build_raw_section(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news):
    now = datetime.now().strftime("%A, %d %b %Y")
    lines = ["\u2600\ufe0f <b>Morning Briefing \u2014 " + now + "</b>\n"]

    fg_num = int(fg_value) if fg_value != "N/A" else 50
    if fg_num <= 25:
        fg_emoji = "\U0001f534"
    elif fg_num <= 45:
        fg_emoji = "\U0001f7e0"
    elif fg_num <= 55:
        fg_emoji = "\U0001f7e1"
    elif fg_num <= 75:
        fg_emoji = "\U0001f7e2"
    else:
        fg_emoji = "\U0001f49a"

    lines.append("\u2501" * 20)
    lines.append("\U0001f9e0 <b>MARKET SENTIMENT</b>")
    lines.append(fg_emoji + " Fear &amp; Greed: <b>" + str(fg_value) + " \u2014 " + str(fg_label) + "</b>")
    lines.append("")
    lines.append("\u2501" * 20)
    lines.append("\U0001f4b0 <b>CRYPTO WATCHLIST</b>")

    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d = prices.get(coin_id, {})
        price = d.get("usd")
        change = d.get("usd_24h_change")
        mcap = d.get("usd_market_cap")
        price_str = "${:,.2f}".format(price) if price else "N/A"
        mcap_str = "${:.1f}B".format(mcap / 1e9) if mcap else ""
        if change is not None:
            arrow = "\u25b2" if change >= 0 else "\u25bc"
            change_str = arrow + " {:.2f}%".format(abs(change))
        else:
            change_str = ""
        lines.append("  <b>" + symbol + "</b>  " + price_str + "  " + change_str + "  <i>" + mcap_str + "</i>")

    lines.append("")
    lines.append("\u2501" * 20)
    lines.append("\U0001f4ca <b>US MACRO DATA</b>")
    new_releases = []

    for label, d in macro.items():
        val = d["value"]
        date = d["date"]
        prev = d["prev"]
        if val is None or val == ".":
            continue
        try:
            val_f = float(val)
            prev_f = float(prev) if prev and prev != "." else None
            val_str = "{:,.2f}".format(val_f)
            if prev_f is not None:
                diff = val_f - prev_f
                arrow = "\u25b2" if diff > 0 else "\u25bc" if diff < 0 else "\u2192"
                change_str = "  " + arrow + " ({:+.2f} vs prev)".format(diff)
            else:
                change_str = ""
        except Exception:
            val_str = str(val)
            change_str = ""
        fresh = "\U0001f195 " if was_released_today(date) else ""
        if was_released_today(date):
            new_releases.append(label)
        lines.append("  " + fresh + "<b>" + label + "</b>: " + val_str + change_str + "  <i>(" + str(date) + ")</i>")

    if new_releases:
        lines.append("\n\U0001f6a8 <b>New today:</b> " + ", ".join(new_releases))
    else:
        lines.append("\n<i>No major US data releases today.</i>")

    lines.append("")
    lines.append("\u2501" * 20)
    lines.append("\U0001f3af <b>POLYMARKET \u2014 TOP BY VOLUME</b>")
    if poly:
        for m in poly:
            vol = "${:.1f}M".format(m["volume"] / 1e6) if m["volume"] >= 1e6 else "${:,.0f}".format(m["volume"])
            yes = "  YES: {:.0f}%".format(m["yes_prob"]) if m["yes_prob"] else ""
            lines.append("  \u2022 <b>" + m["question"][:80] + "</b>" + yes + "  <i>Vol: " + vol + "</i>")
    else:
        lines.append("  Could not load Polymarket data.")

    lines.append("")
    lines.append("\u2501" * 20)
    lines.append("\U0001f30d <b>MACRO NEWS</b>")
    for a in macro_news:
        title = a.get("title", "")[:90]
        url = a.get("url", "")
        source = a.get("source", {}).get("name", "")
        lines.append('  \u2022 <a href="' + url + '">' + title + '</a> <i>(' + source + ')</i>')

    lines.append("")
    lines.append("\u2501" * 20)
    lines.append("\u20bf <b>CRYPTO NEWS</b>")
    for a in crypto_news:
        title = a.get("title", "")[:90]
        url = a.get("url", "")
        source = a.get("source", {}).get("name", "")
        lines.append('  \u2022 <a href="' + url + '">' + title + '</a> <i>(' + source + ')</i>')

    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching data...")
    prices = get_crypto_prices()
    fg_value, fg_label = get_fear_greed()
    macro = get_all_macro()
    poly = get_polymarket_top()
    macro_news = get_news("Federal Reserve OR CPI OR inflation OR GDP OR recession OR FOMC OR ISM PMI", 5)
    crypto_news = get_news("bitcoin OR ethereum OR crypto OR DeFi OR polymarket", 5)

    print("Building message...")
    raw_msg = build_raw_section(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news)

    print("Running AI analysis...")
    ai_analysis = get_groq_analysis(prices, fg_value, fg_label, macro, macro_news, crypto_news, poly)

    ai_header = "\n\n" + "\u2501" * 20 + "\n\U0001f9e0 <b>DRUCKENMILLER ANALYSIS</b>\n" + "\u2501" * 20 + "\n"
    footer = "\n\n" + "\u2501" * 20 + "\n\U0001f916 <i>Auto-briefing \u00b7 CoinGecko \u00b7 FRED \u00b7 Polymarket \u00b7 NewsAPI \u00b7 Groq AI</i>"
    full_message = raw_msg + ai_header + ai_analysis + footer

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("Done!")
