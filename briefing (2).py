import requests
import json
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_BOT_TOKEN = "8734149271:AAHM5T5diwscMnfk7gzGkiRsP-uRbURVcjs"
TELEGRAM_CHAT_ID   = "623392672"
NEWS_API_KEY        = "425b2c8e51244bb9a09880eec07d56fb"
FRED_API_KEY        = "bea607ec27e9abfbb37124f5013e115e"
GROQ_API_KEY        = "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"

CRYPTO_WATCHLIST = {
    "bitcoin": "BTC", "ethereum": "ETH",
    "solana": "SOL", "chainlink": "LINK",
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
    "NMFCI":    "Chicago Fed Conditions",
    "PCEPILFE": "Core PCE",
    "RSAFS":    "Retail Sales",
}
# ============================================================


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
    url = (f"https://api.coingecko.com/api/v3/simple/price"
           f"?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true")
    try:
        return requests.get(url, timeout=10).json()
    except:
        return {}


def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        d = r.json()["data"][0]
        return d["value"], d["value_classification"]
    except:
        return "N/A", "N/A"


def get_fred_latest(series_id):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&sort_order=desc&limit=2")
    try:
        data = requests.get(url, timeout=10).json().get("observations", [])
        if len(data) >= 2:
            return data[0]["value"], data[0]["date"], data[1]["value"]
        elif len(data) == 1:
            return data[0]["value"], data[0]["date"], None
        return None, None, None
    except:
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
    except:
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
            results.append({"question": m.get("question", "Unknown"),
                            "volume": float(m.get("volume", 0)), "yes_prob": yes_price})
        return results
    except:
        return []


def get_news(query, page_size=5):
    try:
        url = (f"https://newsapi.org/v2/everything?q={query}"
               f"&language=en&sortBy=publishedAt&pageSize={page_size}&apiKey={NEWS_API_KEY}")
        return requests.get(url, timeout=10).json().get("articles", [])
    except:
        return []


def get_groq_analysis(prices, fg_value, fg_label, macro, macro_headlines, crypto_headlines, poly):
    # Build raw data summary for the AI
    price_lines = []
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d = prices.get(coin_id, {})
        p = d.get("usd", "N/A")
        c = d.get("usd_24h_change", None)
        change_str = f"{c:+.2f}%" if c is not None else "N/A"
        price_lines.append(f"{symbol}: ${p:,.2f} ({change_str})" if isinstance(p, float) else f"{symbol}: N/A")

    macro_lines = []
    for label, d in macro.items():
        val = d["value"]
        date = d["date"]
        prev = d["prev"]
        if val and val != ".":
            try:
                diff = float(val) - float(prev) if prev and prev != "." else 0
                macro_lines.append(f"{label}: {float(val):.2f} ({diff:+.2f} vs prev) as of {date}")
            except:
                macro_lines.append(f"{label}: {val} as of {date}")

    news_lines = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})"
                  for a in macro_headlines[:5]]
    crypto_lines = [f"- {a.get('title','')} ({a.get('source',{}).get('name','')})"
                    for a in crypto_headlines[:5]]
    poly_lines = [f"- {m['question'][:80]} | YES: {m['yes_prob']:.0f}% | Vol: ${m['volume']/1e6:.1f}M"
                  for m in poly if m['yes_prob']] if poly else ["No data"]

    raw_data = f"""
CRYPTO PRICES (24h):
{chr(10).join(price_lines)}

FEAR & GREED INDEX: {fg_value} — {fg_label}

US MACRO DATA (FRED):
{chr(10).join(macro_lines)}

TOP MACRO HEADLINES:
{chr(10).join(news_lines)}

TOP CRYPTO HEADLINES:
{chr(10).join(crypto_lines)}

POLYMARKET TOP MARKETS:
{chr(10).join(poly_lines)}
"""

    prompt = f"""You are a Lead Macro Analyst reporting directly to Stanley Druckenmiller. 
Your goal is not to report news but to identify Inflection Points and Asymmetrical Risk/Reward setups.
You understand markets are reflexive and narrative drives price until liquidity breaks it.

RULES:
1. Anticipate, Don't React: Tell me what the market is MISPRICING, not what happened.
2. The Fed is the Sun: Filter every event through how it affects the Fed's Reaction Function and global liquidity.
3. The Pig Philosophy: Identify the ONE trade with highest conviction where risk=1, reward=5+.
4. Be brutal and concise. No fluff. Every sentence must have edge.

OUTPUT FORMAT (use these exact section headers):
THEME: [One sentence defining today's macro narrative]

STRATEGIC SENTIMENT: [2-3 sentences using Fear & Greed as CONTRARIAN signal, not momentum]

THE LIQUIDITY BOARD:
Asset | Price | 24h | Macro Implication
[fill for BTC, Gold, Oil, DXY, 10Y Yield - use estimated values if not in data]

THE NARRATIVE GAP: [Where retail/media story differs from smart money/bond market reality]

THE SECOND-ORDER EFFECT: [For the biggest story today, what does this mean 6-12 months out?]

THE PIG TRADE: [The single highest conviction asymmetric setup. Risk 1, Reward 5. Be specific.]

TODAY'S DATA RELEASES TO WATCH: [Any macro data dropping today and what a beat/miss means]

Here is today's raw data:
{raw_data}

Keep total response under 900 words. Be sharp. Think Druckenmiller, not CNBC."""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
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
        return f"AI analysis unavailable: {str(e)}"


def build_raw_section(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news):
    now = datetime.now().strftime("%A, %d %b %Y")
    lines = [f"☀️ <b>Morning Briefing — {now}</b>\n"]

    fg_num = int(fg_value) if fg_value != "N/A" else 50
    fg_emoji = "🔴" if fg_num<=25 else "🟠" if fg_num<=45 else "🟡" if fg_num<=55 else "🟢" if fg_num<=75 else "💚"

    lines += ["━━━━━━━━━━━━━━━━━━━━", "🧠 <b>MARKET SENTIMENT</b>",
              f"{fg_emoji} Fear &amp; Greed: <b>{fg_value} — {fg_label}</b>", ""]

    lines += ["━━━━━━━━━━━━━━━━━━━━", "💰 <b>CRYPTO WATCHLIST</b>"]
    for coin_id, symbol in CRYPTO_WATCHLIST.items():
        d = prices.get(coin_id, {})
        price = d.get("usd")
        change = d.get("usd_24h_change")
        mcap = d.get("usd_market_cap")
        price_str = f"${price:,.2f}" if price else "N/A"
        mcap_str = f"${mcap/1e9:.1f}B" if mcap else ""
        change_str = f"{'▲' if change>=0 else '▼'} {abs(change):.2f}%" if change is not None else ""
        lines.append(f"  <b>{symbol}</b>  {price_str}  {change_str}  <i>{mcap_str}</i>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "📊 <b>US MACRO DATA</b>"]
    new_releases = []
    for label, d in macro.items():
        val, date, prev = d["value"], d["date"], d["prev"]
        if val is None or val == ".": continue
        try:
            val_f = float(val)
            prev_f = float(prev) if prev and prev != "." else None
            val_str = f"{val_f:,.2f}"
            change_str = ""
            if prev_f is not None:
                diff = val_f - prev_f
                arrow = "▲" if diff>0 else "▼" if diff<0 else "→"
                change_str = f"  {arrow} ({diff:+.2f} vs prev)"
        except:
            val_str = str(val); change_str = ""
        fresh = "🆕 " if was_released_today(date) else ""
        if was_released_today(date): new_releases.append(label)
        lines.append(f"  {fresh}<b>{label}</b>: {val_str}{change_str}  <i>({date})</i>")

    lines.append(f"\n🚨 <b>New today:</b> {', '.join(new_releases)}" if new_releases
                 else "\n<i>No major US data releases today.</i>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🎯 <b>POLYMARKET — TOP BY VOLUME</b>"]
    if poly:
        for m in poly:
            vol = f"${m['volume']/1e6:.1f}M" if m['volume']>=1e6 else f"${m['volume']:,.0f}"
            yes = f"  YES: {m['yes_prob']:.0f}%" if m['yes_prob'] else ""
            lines.append(f"  • <b>{m['question'][:80]}</b>{yes}  <i>Vol: {vol}</i>")
    else:
        lines.append("  Could not load Polymarket data.")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🌍 <b>MACRO NEWS</b>"]
    for a in macro_news:
        lines.append(f'  • <a href="{a.get('url','')}">{a.get('title','')[:90]}</a> <i>({a.get('source',{}).get('name','')})</i>')

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "₿ <b>CRYPTO NEWS</b>"]
    for a in crypto_news:
        lines.append(f'  • <a href="{a.get('url','')}">{a.get('title','')[:90]}</a> <i>({a.get('source',{}).get('name','')})</i>')

    return "\n".join(lines)


if __name__ == "__main__":
    print("Fetching data...")
    prices = get_crypto_prices()
    fg_value, fg_label = get_fear_greed()
    macro = get_all_macro()
    poly = get_polymarket_top()
    macro_news = get_news("Federal Reserve OR CPI OR inflation OR GDP OR recession OR FOMC OR ISM PMI", 5)
    crypto_news = get_news("bitcoin OR ethereum OR crypto OR DeFi OR polymarket", 5)

    print("Building raw section...")
    raw_msg = build_raw_section(prices, fg_value, fg_label, macro, poly, macro_news, crypto_news)

    print("Running AI analysis...")
    ai_analysis = get_groq_analysis(prices, fg_value, fg_label, macro, macro_news, crypto_news, poly)

    ai_header = "\n\n━━━━━━━━━━━━━━━━━━━━\n🧠 <b>DRUCKENMILLER ANALYSIS</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    full_message = raw_msg + ai_header + ai_analysis
    footer = "\n\n━━━━━━━━━━━━━━━━━━━━\n🤖 <i>Auto-briefing · CoinGecko · FRED · Polymarket · NewsAPI · Groq AI</i>"
    full_message += footer

    print("Sending to Telegram...")
    send_telegram(full_message)
    print("✅ Done!")
