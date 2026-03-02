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
            
