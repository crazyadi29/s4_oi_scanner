# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  config.py
# ─────────────────────────────────────────────
import os

# ── Telegram ───────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("8615277123:AAH8lbS7p9E3Ef1vZmR02BsVZsa0-5BJGmk", "8615277123:AAH8lbS7p9E3Ef1vZmR02BsVZsa0-5BJGmk")
TELEGRAM_CHAT_ID   = os.getenv("8462499598",   "8462499598")

# ── Fyers ──────────────────────────────────────
FYERS_CLIENT_ID    = "Q7DD93F3RO-100"
FYERS_SECRET_KEY   = "ESMJRJMH6K"
FYERS_REDIRECT_URI = "https://trade.fyers.in/api-login/redirect-uri/index.html"

# ── Strategy settings ──────────────────────────
MIN_MOVE_PCT       = 2.0
SCAN_INTERVAL_SEC  = 8
MAX_STOCKS_PER_RUN = 100
COOLDOWN_MINUTES   = 30
TOP_N_OTM          = 2

# ── Market hours (IST, 24h) ────────────────────
MARKET_OPEN_H  = 9
MARKET_OPEN_M  = 15
MARKET_CLOSE_H = 15
MARKET_CLOSE_M = 30
