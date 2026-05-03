# ─────────────────────────────────────────────
#  S4 — MAX OI SCANNER  |  alerts.py
# ─────────────────────────────────────────────

import requests
import logging
from datetime import datetime

log = logging.getLogger("alerts")


def _fmt_oi(oi: int) -> str:
    """Format OI in lots with commas."""
    return f"{oi:,}"


def _fmt_greek(val) -> str:
    if val == "—" or val is None:
        return "—"
    try:
        return f"{float(val):.4f}"
    except Exception:
        return str(val)


def _fmt_iv(val) -> str:
    if val == "—" or val is None:
        return "—"
    try:
        return f"{float(val):.2f}%"
    except Exception:
        return str(val)


def _time_str() -> str:
    return datetime.now().strftime("%I:%M:%S %p")


def _option_block(opt: dict, label: str) -> str:
    atm_tag = "  ⚡ ATM" if opt.get("is_atm") else ""
    oi_chg  = opt["oi_chg"]
    oi_arrow= "▲" if oi_chg > 0 else ("▼" if oi_chg < 0 else "─")

    return (
        f"\n📊 *{label} — {opt['type']} {opt['strike']:,.0f}*{atm_tag}\n"
        f"  OI        : `{_fmt_oi(opt['oi'])}` lots  {oi_arrow} `{_fmt_oi(abs(oi_chg))}`\n"
        f"  Premium   : `₹{opt['premium']:.2f}`\n"
        f"  Delta     : `{_fmt_greek(opt['delta'])}`\n"
        f"  Gamma     : `{_fmt_greek(opt['gamma'])}`\n"
        f"  IV        : `{_fmt_iv(opt['iv'])}`\n"
        f"  Volume    : `{opt['volume']:,}`\n"
    )


def build_message(stock: dict, oi_result: dict) -> str:
    sym    = stock["symbol"]
    pct    = stock["pct_change"]
    ltp    = stock["ltp"]
    direct = stock["direction"]
    expiry = oi_result["expiry"]
    atm    = oi_result["atm_strike"]

    emoji = "🟢" if direct == "LONG" else "🔴"
    arrow = "📈" if direct == "LONG" else "📉"
    pct_s = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"

    nse_link   = f"https://www.nseindia.com/get-quotes/derivatives?symbol={sym}"
    chart_link = f"https://chartink.com/stocks/{sym}.html"

    lines = [
        f"{emoji} *S4 — MAX OI ALERT* {emoji}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 *{sym}*  |  {arrow} `{pct_s}`",
        f"⏰ `{_time_str()}`",
        f"💰 Spot: `₹{ltp:,.2f}`  |  Expiry: `{expiry}`",
        f"🎯 ATM Strike: `{atm:,.0f}`",
    ]

    ce = oi_result.get("best_ce")
    pe = oi_result.get("best_pe")

    if ce:
        lines.append(_option_block(ce, "MAX OI CALL"))
    if pe:
        lines.append(_option_block(pe, "MAX OI PUT"))

    lines.append(f"\n🔍 [NSE Chain]({nse_link}) | [Chart]({chart_link})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def console_alert(msg: str, stock: dict):
    """Print clean version to terminal."""
    sym = stock["symbol"]
    pct = stock["pct_change"]
    ce  = stock.get("_ce")
    pe  = stock.get("_pe")

    print(f"\n{'='*55}")
    print(f"  S4 ALERT | {sym}  ({'+' if pct>0 else ''}{pct:.2f}%)")
    print(f"{'='*55}")
    if ce:
        print(f"  MAX OI CALL  → Strike {ce['strike']:,.0f} | OI {ce['oi']:,} | "
              f"Δ {_fmt_greek(ce['delta'])} | Γ {_fmt_greek(ce['gamma'])} | ₹{ce['premium']:.2f}")
    if pe:
        print(f"  MAX OI PUT   → Strike {pe['strike']:,.0f} | OI {pe['oi']:,} | "
              f"Δ {_fmt_greek(pe['delta'])} | Γ {_fmt_greek(pe['gamma'])} | ₹{pe['premium']:.2f}")
    print(f"{'='*55}\n")


def send_telegram(token: str, chat_id: str, msg: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    chat_id,
            "text":       msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=10)
        if r.status_code == 200:
            return True
        log.warning(f"Telegram error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
    return False
