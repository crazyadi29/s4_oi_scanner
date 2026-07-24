# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  formatter.py
# ─────────────────────────────────────────────

from datetime import datetime


def _lacs(oi: int) -> str:
    return f"{oi / 1_00_000:.2f}L"

def _lacs_chg(oi_chg: float) -> str:
    prefix = "+" if oi_chg >= 0 else "-"
    return f"{prefix}{abs(oi_chg) / 1_00_000:.2f}L"

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


# ── signal metadata ────────────────────────────
_SIGNAL_META = {
    "LONG_BUILDUP":   {"emoji": "🟢", "label": "LONG BUILDUP",   "desc": "Price ↑ + CE OI buildup ↑ → Bulls adding fresh longs"},
    "SHORT_COVERING": {"emoji": "🔵", "label": "SHORT COVERING",  "desc": "Price ↑ + CE OI chg ↓ → Bears covering shorts"},
    "SHORT_BUILDUP":  {"emoji": "🔴", "label": "SHORT BUILDUP",   "desc": "Price ↓ + PE OI buildup ↑ → Bears adding fresh shorts"},
    "LONG_UNWINDING": {"emoji": "🟠", "label": "LONG UNWINDING",  "desc": "Price ↓ + PE OI chg ↓ → Bulls exiting longs"},
}


def _opt_row(rank: int, opt: dict) -> str:
    medal = ["1️⃣", "2️⃣", "3️⃣"][rank] if rank < 3 else f"{rank+1}."
    return (
        f"  {medal} *{opt['strike']:,.0f}*  |  "
        f"OI: `{_lacs(opt['oi'])}`  ΔOI: `{_lacs_chg(opt['oi_chg'])}`\n"
        f"       Prem: `₹{opt['premium']:.2f}`  "
        f"Δ: `{_greek(opt['delta'])}`  "
        f"IV: `{_iv(opt['iv'])}`"
    )


def build_alert(stock: dict, result: dict) -> str:
    sym          = stock["symbol"]
    pct          = stock["pct"]
    ltp          = stock["ltp"]
    expiry       = result["expiry"]
    atm          = result["atm_strike"]
    signal_type  = result.get("signal_type", "LONG_BUILDUP")
    option_side  = result.get("option_side", "CALL")
    institutional= result.get("institutional", False)
    ce_oi_chg    = result.get("ce_oi_chg", 0)
    pe_oi_chg    = result.get("pe_oi_chg", 0)
    ce_oi        = result.get("ce_oi", 0)
    pe_oi        = result.get("pe_oi", 0)

    meta   = _SIGNAL_META.get(signal_type, _SIGNAL_META["LONG_BUILDUP"])
    emoji  = meta["emoji"]
    label  = meta["label"]
    desc   = meta["desc"]
    pct_s  = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
    arrow  = "📈" if pct > 0 else "📉"

    nse_url   = f"https://www.nseindia.com/get-quotes/derivatives?symbol={sym}"
    chart_url = f"https://chartink.com/stocks/{sym}.html"

    lines = [
        f"{emoji}{emoji} *{label}* {emoji}{emoji}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 *{sym}*  {arrow}  `{pct_s}`",
        f"💡 _{desc}_",
        f"⏰ `{_time_now()}`   💰 Spot: `₹{ltp:,.2f}`",
        f"📅 Expiry: `{expiry}`   🎯 ATM: `{atm:,.0f}`",
        f"",
    ]

    if institutional:
        lines.insert(3, f"🏦 *INSTITUTIONAL CONVICTION* — OI chg ≥15% + Vol 1.9x")

    # OI summary
    lines.append(f"📊 *OI Summary*")
    lines.append(f"  CE OI: `{_lacs(ce_oi)}`  ΔCE: `{_lacs_chg(ce_oi_chg)}`")
    lines.append(f"  PE OI: `{_lacs(pe_oi)}`  ΔPE: `{_lacs_chg(pe_oi_chg)}`")
    lines.append(f"")

    # top options block
    if option_side == "CALL":
        ce_top = result.get("ce_top", [])
        if ce_top:
            lines.append(f"🔼 *TOP OTM CALLS (CE)*")
            for i, o in enumerate(ce_top):
                lines.append(_opt_row(i, o))
            lines.append("")
    else:
        pe_top = result.get("pe_top", [])
        if pe_top:
            lines.append(f"🔽 *TOP OTM PUTS (PE)*")
            for i, o in enumerate(pe_top):
                lines.append(_opt_row(i, o))
            lines.append("")

    lines.append(f"🔗 [NSE Chain]({nse_url}) | [Chart]({chart_url})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def build_tracking_update(sym: str, strike: float, option_side: str,
                          entry_prem: float, curr_prem: float,
                          pnl: float, lot_size: int, signal_type: str) -> str:
    prem_pct  = (curr_prem - entry_prem) / entry_prem * 100 if entry_prem else 0
    pnl_emoji = "🔥🔥🔥" if pnl > 0 else "🩸🩸🩸"
    direction = "profit" if pnl > 0 else "loss"
    arrow     = "📈" if pnl > 0 else "📉"

    meta  = _SIGNAL_META.get(signal_type, _SIGNAL_META["LONG_BUILDUP"])
    emoji = meta["emoji"]

    lines = [
        f"{emoji} *{sym}* — {strike:,.0f} {option_side}  {arrow}",
        f"Bought at `₹{entry_prem:.2f}`",
        f"`₹{curr_prem:.2f}` now {pnl_emoji}  `{prem_pct:+.1f}%`",
        f"₹{abs(pnl):,.0f} {direction} in {lot_size} lot  ⏰ `{_time_now()}`",
    ]

    return "\n".join(lines)


def console_print(stock: dict, result: dict):
    sym         = stock["symbol"]
    pct         = stock["pct"]
    signal_type = result.get("signal_type", "")
    option_side = result.get("option_side", "")
    w           = 60
    sep         = "=" * w
    print(f"\n{sep}")
    print(f"  {signal_type} ({option_side}) | {sym}  ({'+' if pct>0 else ''}{pct:.2f}%)  |  {_time_now()}")
    print(f"  Spot ₹{stock['ltp']:,.2f}  |  ATM {result['atm_strike']:,.0f}  |  Expiry {result['expiry']}")
    if result.get("institutional"):
        print(f"  🏦 INSTITUTIONAL CONVICTION")
    print(sep + "\n")


# ── EOD summary ────────────────────────────────
def build_eod_summary(results: list[dict]) -> str:
    from datetime import date

    today     = date.today().strftime("%d-%b-%Y")
    medals    = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟",
                 "1️⃣1️⃣","1️⃣2️⃣","1️⃣3️⃣","1️⃣4️⃣","1️⃣5️⃣"]

    # sort by return % descending
    def _ret(r):
        e = r["entry_prem"]
        return (r["exit_prem"] - e) / e * 100 if e else 0

    results = sorted(results, key=_ret, reverse=True)

    lines = [
        f"🚨🔥 *S4 BOT – TRADE SUMMARY {today}* 🔥🚨",
        f"📅 Live Market Performance | Intraday Only",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *OPTION CALLS*",
        f"",
    ]

    winners  = 0
    losers   = 0
    total_ret = 0.0

    for i, r in enumerate(results):
        entry    = r["entry_prem"]
        exit_    = r["exit_prem"]
        ret_pct  = (exit_ - entry) / entry * 100 if entry else 0
        total_ret += ret_pct
        medal    = medals[i] if i < len(medals) else f"{i+1}."

        if ret_pct >= 100:
            tag = "💥"
        elif ret_pct >= 40:
            tag = "🚀"
        elif ret_pct >= 15:
            tag = "⚡️"
        elif ret_pct >= 0:
            tag = "✅"
        else:
            tag = "🔴"

        arrow = "📈" if ret_pct >= 0 else "📉"

        if ret_pct >= 0:
            winners += 1
        else:
            losers += 1

        lines.append(
            f"{medal} *{r['symbol']}* {r['strike']:,.0f} {r['option_side']} "
            f"🎯 `{entry:.2f}` ➝ `{exit_:.2f}` {arrow} "
            f"Return: `{ret_pct:+.1f}%` {tag}"
        )

    avg_ret = total_ret / len(results) if results else 0

    lines += [
        f"",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📈 Winners: *{winners}*  |  📉 Losers: *{losers}*",
        f"⚡️ Avg Return: `{avg_ret:+.1f}%`",
        f"🕒 Session closed: `3:30 PM IST`",
    ]

    return "\n".join(lines)
