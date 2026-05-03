# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  config.py
# ─────────────────────────────────────────────
import os

# ── Telegram ───────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("8615277123:AAH8lbS7p9E3Ef1vZmR02BsVZsa0-5BJGmk", "8615277123:AAH8lbS7p9E3Ef1vZmR02BsVZsa0-5BJGmk")
TELEGRAM_CHAT_ID   = os.getenv("8615277123",   "8615277123")

# ── Strategy settings ──────────────────────────
MIN_MOVE_PCT       = 1.0    # alert when stock moves > this %
SCAN_INTERVAL_SEC  = 8      # scan every N seconds (fast detection)
MAX_STOCKS_PER_RUN = 40     # max movers to process per cycle
COOLDOWN_MINUTES   = 30     # re-alert same stock after 30 min
TOP_N_OTM          = 2      # show top N OTM strikes per side

# ── Market hours (IST, 24h) ────────────────────
MARKET_OPEN_H  = 9
MARKET_OPEN_M  = 15
MARKET_CLOSE_H = 15
MARKET_CLOSE_M = 30
