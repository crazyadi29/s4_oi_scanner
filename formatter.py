# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  formatter.py
# ─────────────────────────────────────────────

from datetime import datetime


def _lacs(oi: int) -> str:
    """Convert OI to lakhs string, e.g. 12.45L"""
    val = oi / 1_00_000
    return f"{val:.2f}L"


def _lacs_chg(oi_chg: int) -> str:
    prefix = "+" if oi_chg >= 0 else "-"
    val    = abs(oi_chg) / 1_00_000
    return f"{prefix}{val:.2f}L"


def _greek(val) -> str:
    if val in ("—", None, ""):
        return "—"
    try:
        return f"{float(val):.4f}"
    except Exception:
        return str(val)


def _iv(val) -> str:
    if val in ("—", None, ""):
        return "—"
    try:
        return f"{float(val):.1f}%"
    except Exception:
        return str(val)


def _time_now() -> str:
    return datetime.now().strftime("%I:%M:%S %p")


# ── single option row ──────────────────────────
def _opt_row(rank: int, opt: dict) -> str:
    medal = ["1️⃣", "2️⃣", "3️⃣"][rank] if rank < 3 else f"{rank+1}."
    oi_chg_str = _lacs_chg(opt["oi_chg"])
    return (
        f"  {medal} *{opt['strike']:,.0f}*  |  "
        f"OI: `{_lacs(opt['oi'])}`  ΔOI: `{oi_chg_str}`\n"
        f"       Prem: `₹{opt['premium']:.2f}`  "
        f"Δ: `{_greek(opt['delta'])}`  "
        f"Γ: `{_greek(opt['gamma'])}`  "
        f"IV: `{_iv(opt['iv'])}`"
    )


# ── full alert message ──────────────────────────
def build_alert(stock: dict, result: dict) -> str:
    sym    = stock["symbol"]
    pct    = stock["pct"]
    ltp    = stock["ltp"]
    expiry = result["expiry"]
    atm    = result["atm_strike"]

    arrow  = "📈" if pct > 0 else "📉"
    pct_s  = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
    emoji  = "🟢" if pct > 0 else "🔴"

    nse_url   = f"https://www.nseindia.com/get-quotes/derivatives?symbol={sym}"
    chart_url = f"https://chartink.com/stocks/{sym}.html"

    lines = [
        f"{emoji}{emoji} *{sym}* {arrow} `{pct_s}` {emoji}{emoji}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ `{_time_now()}`   💰 Spot: `₹{ltp:,.2f}`",
        f"📅 Expiry: `{expiry}`   🎯 ATM: `{atm:,.0f}`",
        f"",
    ]

    # ── CE block ──
    ce_top = result.get("ce_top", [])
    if ce_top:
        lines.append("🔼 *TOP OTM CALLS (CE)*")
        for i, opt in enumerate(ce_top):
            lines.append(_opt_row(i, opt))
        lines.append("")

    # ── PE block ──
    pe_top = result.get("pe_top", [])
    if pe_top:
        lines.append("🔽 *TOP OTM PUTS (PE)*")
        for i, opt in enumerate(pe_top):
            lines.append(_opt_row(i, opt))
        lines.append("")

    lines.append(f"🔗 [NSE Chain]({nse_url}) | [Chart]({chart_url})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


# ── console version ────────────────────────────
def console_print(stock: dict, result: dict):
    sym = stock["symbol"]
    pct = stock["pct"]
    w   = 58
    sep = "=" * w
    print(f"\n{sep}")
    print(f"  S4 | {sym}  ({'+' if pct>0 else ''}{pct:.2f}%)  |  {_time_now()}")
    print(f"  Spot ₹{stock['ltp']:,.2f}  |  ATM {result['atm_strike']:,.0f}  |  Expiry {result['expiry']}")
    print(sep)

    for label, key in [("TOP OTM CALLS (CE)", "ce_top"), ("TOP OTM PUTS (PE)", "pe_top")]:
        opts = result.get(key, [])
        if opts:
            print(f"  {label}")
            for i, o in enumerate(opts, 1):
                print(
                    f"    {i}. Strike {o['strike']:,.0f}  "
                    f"OI {_lacs(o['oi'])}  ΔOI {_lacs_chg(o['oi_chg'])}  "
                    f"Prem ₹{o['premium']:.2f}  "
                    f"Delta {_greek(o['delta'])}  Gamma {_greek(o['gamma'])}"
                )
    print(sep + "\n")
