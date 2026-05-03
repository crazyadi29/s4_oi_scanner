# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  scanner.py
# ─────────────────────────────────────────────

import asyncio
import logging
from datetime import datetime, timedelta, time as dtime

import config
from nse_client import NSEClient
from formatter  import build_alert, console_print

log = logging.getLogger("scanner")

# ── cooldown tracker ───────────────────────────
_last_alerted: dict[str, datetime] = {}

def _on_cooldown(sym: str) -> bool:
    t = _last_alerted.get(sym)
    if t is None:
        return False
    return datetime.now() - t < timedelta(minutes=config.COOLDOWN_MINUTES)

def _set_cooldown(sym: str):
    _last_alerted[sym] = datetime.now()

def _cooldown_remaining(sym: str) -> str:
    t = _last_alerted.get(sym)
    if not t:
        return "0m"
    secs = (timedelta(minutes=config.COOLDOWN_MINUTES) - (datetime.now() - t)).total_seconds()
    return f"{max(0, int(secs // 60))}m"


# ── market hours ───────────────────────────────
def market_open() -> bool:
    now   = datetime.now().time()
    start = dtime(config.MARKET_OPEN_H,  config.MARKET_OPEN_M)
    end   = dtime(config.MARKET_CLOSE_H, config.MARKET_CLOSE_M)
    return start <= now <= end


# ── Scanner ────────────────────────────────────
class Scanner:
    def __init__(self, send_fn):
        """send_fn: async callable(text: str, stock: dict)"""
        self.send     = send_fn
        self.nse      = NSEClient()
        self._running = False
        self._task    = None

    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task    = asyncio.create_task(self._loop())
        log.info("Scanner started ✅")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Scanner stopped 🛑")

    # ── main loop ──────────────────────────────
    async def _loop(self):
        while self._running:
            try:
                if market_open():
                    await self._scan_cycle()
                    # scan fast — only a short sleep between cycles
                    await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                else:
                    # market closed — check every 20s for open
                    log.info("Market closed — waiting for 9:15 AM …")
                    await asyncio.sleep(20)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Loop error: {e}")
                await asyncio.sleep(5)

    # ── one scan cycle ─────────────────────────
    async def _scan_cycle(self):
        movers = await asyncio.to_thread(
            self.nse.get_fo_movers, config.MIN_MOVE_PCT
        )
        movers = movers[:config.MAX_STOCKS_PER_RUN]

        if not movers:
            return

        new_movers = [s for s in movers if not _on_cooldown(s["symbol"])]
        if not new_movers:
            return

        log.info(f"New movers: {len(new_movers)} — firing alerts …")

        # fire all new movers concurrently for max speed
        tasks = [self._process_stock(stock) for stock in new_movers]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── per-stock processing ───────────────────
    async def _process_stock(self, stock: dict):
        sym = stock["symbol"]
        try:
            chain = await asyncio.to_thread(self.nse.get_option_chain, sym)
            if not chain:
                return

            result = await asyncio.to_thread(
                self.nse.find_top_otm, chain, stock["ltp"], config.TOP_N_OTM
            )
            if not result:
                return

            if not result["ce_top"] and not result["pe_top"]:
                return

            msg = build_alert(stock, result)
            console_print(stock, result)

            # send to Telegram immediately
            await self.send(msg, stock)
            _set_cooldown(sym)
            log.info(f"[{sym}] ✅ Signal sent | cooldown {config.COOLDOWN_MINUTES}m")

        except Exception as e:
            log.error(f"[{sym}] error: {e}")
