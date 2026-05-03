#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  main.py
# ─────────────────────────────────────────────

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import config
from scanner import Scanner, market_open

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# ── globals ────────────────────────────────────
_scanner: Scanner | None = None
_signal_count: int = 0
_session_signals: list[dict] = []


# ── send helper ────────────────────────────────
async def _telegram_send(app: Application, text: str):
    try:
        await app.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.error(f"Telegram send error: {e}")


# ── last session summary ───────────────────────
def _build_session_summary() -> str:
    if not _session_signals:
        return (
            "📭 *No signals from last session.*\n"
            "Either no stocks moved >1% or scanner was not running."
        )
    lines = [
        f"📋 *Last Session Data*  ({len(_session_signals)} signals)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for s in _session_signals[-10:]:
        arrow = "📈" if s["pct"] > 0 else "📉"
        pct_s = f"+{s['pct']:.2f}%" if s["pct"] > 0 else f"{s['pct']:.2f}%"
        lines.append(f"{arrow} *{s['symbol']}*  `{pct_s}`  ⏰ `{s['time']}`")
    if len(_session_signals) > 10:
        lines.append(f"_... and {len(_session_signals) - 10} more_")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Use /lastdata to see the last full signal.")
    return "\n".join(lines)


def _signal_count_inc():
    global _signal_count
    _signal_count += 1


# ── /startscan ─────────────────────────────────
async def cmd_startscan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global _scanner, _signal_count, _session_signals

    async def send_fn(text: str, stock: dict):
        _session_signals.append({
            "symbol": stock["symbol"],
            "pct":    stock["pct"],
            "time":   datetime.now().strftime("%I:%M %p"),
            "msg":    text,
        })
        _signal_count_inc()
        await _telegram_send(ctx.application, text)

    if not market_open():
        summary = _build_session_summary()
        await update.message.reply_text(
            "🔴 *Market is Currently Closed*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Market hours: *9:15 AM – 3:30 PM* (Mon–Fri)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + summary,
            parse_mode="Markdown"
        )
        if not (_scanner and _scanner.is_running()):
            _scanner = Scanner(send_fn=send_fn)
            await _scanner.start()
            await update.message.reply_text(
                "⏳ Scanner *armed* — will fire automatically at 9:15 AM.",
                parse_mode="Markdown"
            )
        return

    if _scanner and _scanner.is_running():
        await update.message.reply_text(
            "⚡ Scanner is *already running!*",
            parse_mode="Markdown"
        )
        return

    _signal_count = 0
    _session_signals = []

    await update.message.reply_text(
        "🟢 *Market is OPEN*\n"
        "🚀 *S4 — MAX OI Scanner Started!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Trigger  : stocks moving `>{config.MIN_MOVE_PCT}%`\n"
        f"⏱ Interval : every `{config.SCAN_INTERVAL_SEC}` seconds\n"
        f"🔝 OTM shown: top `{config.TOP_N_OTM}` per side\n"
        f"⏳ Cooldown : `{config.COOLDOWN_MINUTES}` min per stock\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Signals fire automatically. Use /stopscan to pause.",
        parse_mode="Markdown"
    )

    _scanner = Scanner(send_fn=send_fn)
    await _scanner.start()


# ── /stopscan ──────────────────────────────────
async def cmd_stopscan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global _scanner
    if not _scanner or not _scanner.is_running():
        await update.message.reply_text("ℹ️ Scanner is not running. Use /startscan to begin.")
        return
    await _scanner.stop()
    await update.message.reply_text(
        f"🛑 *Scanner Stopped.*\n"
        f"Signals this session: `{_signal_count}`\n"
        "Use /startscan to resume anytime.",
        parse_mode="Markdown"
    )


# ── /status ────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    running  = _scanner and _scanner.is_running()
    mkt_open = market_open()
    now_str  = datetime.now().strftime("%I:%M:%S %p")

    await update.message.reply_text(
        f"📡 *S4 Scanner Status*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Scanner : {'🟢 Running' if running else '🔴 Stopped'}\n"
        f"Market  : {'🟢 Open' if mkt_open else '🔴 Closed'}\n"
        f"Time    : `{now_str}`\n"
        f"Trigger : `>{config.MIN_MOVE_PCT}%` move\n"
        f"Interval: `{config.SCAN_INTERVAL_SEC}s`\n"
        f"Cooldown: `{config.COOLDOWN_MINUTES} min`\n"
        f"Signals : `{_signal_count}` this session\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )


# ── /lastdata ──────────────────────────────────
async def cmd_lastdata(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _session_signals:
        await update.message.reply_text("⚠️ No signals yet. Run /startscan first.")
        return
    last = _session_signals[-1]
    await update.message.reply_text(
        f"📊 *Session Summary*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 Total Signals : `{_signal_count}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Last Signal:*\n\n{last['msg']}",
        parse_mode="Markdown"
    )


# ── /help ──────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *S4 — MAX OI Scanner Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "/startscan — start scanner\n"
        "/stopscan  — pause the scanner\n"
        "/status    — current state\n"
        "/lastdata  — last signal + session count\n"
        "/help      — this message\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Fires the moment a stock moves >1%.\n"
        "Top 2 OTM CE + PE shown with OI in Lakhs.",
        parse_mode="Markdown"
    )


# ── startup / shutdown ─────────────────────────
async def on_startup(app: Application):
    log.info("Bot online ✅")
    try:
        await app.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text="🤖 *S4 OI Scanner Bot is online!*\nSend /startscan to begin.",
            parse_mode="Markdown"
        )
    except Exception as e:
        log.warning(f"Startup message failed: {e}")


async def on_shutdown(app: Application):
    global _scanner
    if _scanner and _scanner.is_running():
        await _scanner.stop()
    log.info("Bot shut down 🛑")


# ── entry point ────────────────────────────────
async def main():
    log.info("=" * 55)
    log.info("  S4 — MAX OI SCANNER BOT  |  Starting …")
    log.info("=" * 55)

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("startscan", cmd_startscan))
    app.add_handler(CommandHandler("stopscan",  cmd_stopscan))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("lastdata",  cmd_lastdata))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("start",     cmd_help))

    log.info("Polling started — waiting for commands …")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
