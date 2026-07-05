# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  scanner.py
# ─────────────────────────────────────────────

import asyncio
import logging
from datetime import datetime, timedelta, time as dtime

import pytz

import config

IST = pytz.timezone('Asia/Kolkata')

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
    now   = datetime.now(IST).time()
    start = dtime(config.MARKET_OPEN_H,  config.MARKET_OPEN_M)
    end   = dtime(config.MARKET_CLOSE_H, config.MARKET_CLOSE_M)
    return start <= now <= end


# ── OI change cache ────────────────────────────
# stores: { symbol: [(timestamp, ce_oi_chg, pe_oi_chg), ...] }
# keeps last 20 mins of snapshots per symbol, pruned every cycle
OI_CHG_WINDOW_MINS = 15
_oi_chg_history: dict[str, list[tuple[datetime, float, float]]] = {}

def _record_oi_chg(sym: str, ce_oi_chg: float, pe_oi_chg: float):
    now = datetime.now()
    if sym not in _oi_chg_history:
        _oi_chg_history[sym] = []
    _oi_chg_history[sym].append((now, ce_oi_chg, pe_oi_chg))
    # prune older than 20 mins
    cutoff = now - timedelta(minutes=20)
    _oi_chg_history[sym] = [e for e in _oi_chg_history[sym] if e[0] >= cutoff]


def _oi_chg_increased(sym: str, current_ce_chg: float, current_pe_chg: float, signal: str) -> bool:
    """
    Compare current OI change vs snapshot ~15 mins ago.
    CALL: current_ce_chg > ce_chg_15m_ago
    PUT : current_pe_chg > pe_chg_15m_ago
    Returns True if no history yet (first 15 mins — let it pass).
    """
    history = _oi_chg_history.get(sym, [])
    if not history:
        return True  # no history yet, pass through

    now     = datetime.now()
    cutoff  = now - timedelta(minutes=OI_CHG_WINDOW_MINS)

    # find the oldest snapshot within the 15-min window
    past_snaps = [e for e in history if e[0] <= cutoff]
    if not past_snaps:
        return True  # less than 15 mins of data, pass through

    # closest snapshot to exactly 15 mins ago
    ref = min(past_snaps, key=lambda e: abs((e[0] - cutoff).total_seconds()))
    _, ref_ce_chg, ref_pe_chg = ref

    if signal == "CALL":
        result = current_ce_chg > ref_ce_chg
        log.info(f"[{sym}] CE OI chg: now={current_ce_chg:,.0f}  15m_ago={ref_ce_chg:,.0f}  increased={result}")
        return result
    else:  # PUT
        result = current_pe_chg > ref_pe_chg
        log.info(f"[{sym}] PE OI chg: now={current_pe_chg:,.0f}  15m_ago={ref_pe_chg:,.0f}  increased={result}")
        return result


# ── Scanner ────────────────────────────────────
class Scanner:
    def __init__(self, send_fn):
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
                    await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                else:
                    log.info("Market closed — waiting ...")
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

        log.info(f"Total movers >{config.MIN_MOVE_PCT}%: {len(movers)}")

        new_movers = [s for s in movers if not _on_cooldown(s["symbol"])]

        log.info(f"After cooldown filter: {len(new_movers)} | Skipped: {len(movers) - len(new_movers)}")

        if not new_movers:
            log.info("All movers on cooldown — no alerts this cycle")
            return

        tasks = [self._process_stock(stock) for stock in new_movers]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── per-stock processing ───────────────────
    async def _process_stock(self, stock: dict):
        sym = stock["symbol"]
        pct = stock["pct"]
        try:
            chain = await asyncio.to_thread(self.nse.get_option_chain, sym)
            if not chain:
                log.warning(f"[{sym}] option chain = None")
                return

            result = await asyncio.to_thread(
                self.nse.find_top_otm, chain, stock["ltp"], config.TOP_N_OTM
            )
            if not result:
                log.warning(f"[{sym}] find_top_otm returned None")
                return

            if not result["ce_top"] and not result["pe_top"]:
                log.warning(f"[{sym}] no CE/PE data found in chain")
                return

            # ── compute top 2 OI and OI change sums ───
            ce_oi     = sum(o["oi"]     for o in result["ce_top"])
            pe_oi     = sum(o["oi"]     for o in result["pe_top"])
            ce_oi_chg = sum(o["oi_chg"] for o in result["ce_top"])
            pe_oi_chg = sum(o["oi_chg"] for o in result["pe_top"])

            # record snapshot for 15-min comparison
            _record_oi_chg(sym, ce_oi_chg, pe_oi_chg)

            # ── determine signal direction ─────────────
            if pct >= config.MIN_MOVE_PCT:
                signal = "CALL"
            elif pct <= -config.MIN_MOVE_PCT:
                signal = "PUT"
            else:
                return  # shouldn't happen but safety check

            # ── filter 1: OI ratio ─────────────────────
            if signal == "CALL" and ce_oi <= pe_oi:
                log.info(f"[{sym}] CALL skipped — CE OI ({ce_oi:,}) <= PE OI ({pe_oi:,})")
                return
            if signal == "PUT" and pe_oi <= ce_oi:
                log.info(f"[{sym}] PUT skipped — PE OI ({pe_oi:,}) <= CE OI ({ce_oi:,})")
                return

            # ── filter 2: OI change increasing vs 15m ago
            if not _oi_chg_increased(sym, ce_oi_chg, pe_oi_chg, signal):
                log.info(f"[{sym}] {signal} skipped — OI change not increasing vs 15m ago")
                return

            # ── all filters passed — fire signal ───────
            result["signal"] = signal
            msg = build_alert(stock, result)
            console_print(stock, result)
            await self.send(msg, stock)
            _set_cooldown(sym)
            log.info(f"[{sym}] ✅ {signal} signal sent | cooldown {config.COOLDOWN_MINUTES}m")

        except Exception as e:
            log.error(f"[{sym}] error: {e}")
