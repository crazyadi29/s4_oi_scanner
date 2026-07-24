# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  config.py
# ─────────────────────────────────────────────
import os

# ── Telegram ───────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN:
    raise EnvironmentError(
        "Missing required environment variable: TELEGRAM_BOT_TOKEN. "
        "Set it in your Railway project settings (or .env locally)."
    )
if not TELEGRAM_CHAT_ID:
    raise EnvironmentError(
        "Missing required environment variable: TELEGRAM_CHAT_ID. "
        "Set it in your Railway project settings (or .env locally)."
    )

# ── Fyers ──────────────────────────────────────
FYERS_CLIENT_ID    = os.getenv("FYERS_APP_ID", "Q7DD93F3RO-100")
FYERS_SECRET_KEY   = os.getenv("FYERS_SECRET_KEY", "ESMJRJMH6K")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "https://trade.fyers.in/api-login/redirect-uri/index.html")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "")

# ── Strategy settings ──────────────────────────
MIN_MOVE_PCT       = 1
SCAN_INTERVAL_SEC  = 8
MAX_STOCKS_PER_RUN = 100
COOLDOWN_MINUTES   = 30
TOP_N_OTM          = 2

# ── Market hours (IST, 24h) ────────────────────
MARKET_OPEN_H  = 9
MARKET_OPEN_M  = 15
MARKET_CLOSE_H = 15
MARKET_CLOSE_M = 30
