# S4 — MAX OI Scanner Bot

Telegram bot that scans F&O stocks in real-time.
Fires an alert the moment any stock moves **>1%**, showing the
**top 2 OTM strikes by Open Interest** on both CE and PE sides.

---

## Alert Format

```
🟢🟢 RELIANCE 📈 +2.3% 🟢🟢
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 09:22:14 AM   💰 Spot: ₹2,850.00
📅 Expiry: 08-May-2025   🎯 ATM: 2850

🔼 TOP OTM CALLS (CE)
  1️⃣ 2900  |  OI: 12.45L  ΔOI: +1.23L
       Prem: ₹45.50  Δ: 0.3210  Γ: 0.0012  IV: 18.5%
  2️⃣ 2950  |  OI: 8.32L   ΔOI: +0.45L
       Prem: ₹28.00  Δ: 0.1800  Γ: 0.0008  IV: 17.2%

🔽 TOP OTM PUTS (PE)
  1️⃣ 2800  |  OI: 10.12L  ΔOI: +2.10L
       Prem: ₹38.00  Δ: -0.2800  Γ: 0.0010  IV: 19.1%
  2️⃣ 2750  |  OI: 6.85L   ΔOI: +0.90L
       Prem: ₹22.00  Δ: -0.1500  Γ: 0.0007  IV: 16.8%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Bot Commands

| Command | Action |
|---|---|
| `/startscan` | Start the scanner |
| `/stopscan` | Pause the scanner |
| `/status` | Show current state |
| `/help` | Show commands |

---

## Local Setup (Python only, no Railway)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Set credentials in config.py
TELEGRAM_BOT_TOKEN = "your_token"
TELEGRAM_CHAT_ID   = "your_chat_id"

# 3. Run
python main.py

# 4. Open Telegram → send /startscan
```

---

## Railway Setup

1. Push this folder to a **GitHub repo**
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**
3. Add environment variables in Railway → **Variables**:
   ```
   TELEGRAM_BOT_TOKEN = your_token
   TELEGRAM_CHAT_ID   = your_chat_id
   ```
4. Railway auto-reads `Procfile` → runs `python main.py`
5. Open Telegram → send `/startscan`

> **Note:** `config.py` reads from `os.getenv(...)` first, so Railway env vars override the defaults automatically.

---

## File Structure

```
s4_oi_scanner/
├── main.py          ← bot entry point + command handlers
├── scanner.py       ← scan loop, cooldown logic
├── nse_client.py    ← NSE API wrapper, top-2 OTM finder
├── formatter.py     ← Telegram + console message builder
├── config.py        ← all settings
├── requirements.txt
├── Procfile         ← Railway worker config
└── .env.example     ← env vars template
```

---

## Settings (config.py)

| Setting | Default | What it does |
|---|---|---|
| `MIN_MOVE_PCT` | `1.0` | Alert threshold |
| `SCAN_INTERVAL_SEC` | `8` | How often to scan |
| `COOLDOWN_MINUTES` | `30` | Re-alert same stock after |
| `TOP_N_OTM` | `2` | OTM strikes shown per side |
| `MAX_STOCKS_PER_RUN` | `40` | Cap to avoid NSE blocks |
