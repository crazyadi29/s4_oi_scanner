# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  scanner.py
# ─────────────────────────────────────────────

import asyncio
import logging
from datetime import datetime, timedelta, time as dtime

import pytz
import config
from nse_client import NSEClient
from formatter  import build_alert, build_tracking_update, console_print

log = logging.getLogger("scanner")
IST = pytz.timezone('Asia/Kolkata')

# ── cooldown ───────────────────────────────────
_last_alerted: dict[str, datetime] = {}

def _on_cooldown(sym: str) -> bool:
    t = _last_alerted.get(sym)
    return False if t is None else datetime.now() - t < timedelta(minutes=config.COOLDOWN_MINUTES)

def _set_cooldown(sym: str):
    _last_alerted[sym] = datetime.now()

# ── market hours ───────────────────────────────
def market_open() -> bool:
    now   = datetime.now(IST).time()
    start = dtime(config.MARKET_OPEN_H,  config.MARKET_OPEN_M)
    end   = dtime(config.MARKET_CLOSE_H, config.MARKET_CLOSE_M)
    return start <= now <= end

# ── OI change cache (1-min window) ────────────
OI_CHG_WINDOW_MINS = 1
_oi_chg_history: dict[str, list[tuple[datetime, float, float]]] = {}

def _record_oi_chg(sym: str, ce_oi_chg: float, pe_oi_chg: float):
    now = datetime.now()
    if sym not in _oi_chg_history:
        _oi_chg_history[sym] = []
    _oi_chg_history[sym].append((now, ce_oi_chg, pe_oi_chg))
    cutoff = now - timedelta(minutes=5)
    _oi_chg_history[sym] = [e for e in _oi_chg_history[sym] if e[0] >= cutoff]

def _get_ref_oi_chg(sym: str) -> tuple[float, float] | None:
    """Return (ce_oi_chg, pe_oi_chg) from ~1 min ago. None if not enough history."""
    history = _oi_chg_history.get(sym, [])
    if not history:
        return None
    now    = datetime.now()
    cutoff = now - timedelta(minutes=OI_CHG_WINDOW_MINS)
    past   = [e for e in history if e[0] <= cutoff]
    if not past:
        return None
    ref = min(past, key=lambda e: abs((e[0] - cutoff).total_seconds()))
    return ref[1], ref[2]

# ── active signals tracker ─────────────────────
# { symbol: { "signal_type", "strike", "option_type", "entry_premium",
#             "lot_size", "entry_ltp", "last_premium" } }
_active_signals: dict[str, dict] = {}

# ── signal classification ──────────────────────
def _classify_signal(pct: float, ce_oi_chg_now: float, pe_oi_chg_now: float,
                     ref: tuple[float, float] | None) -> tuple[str, str] | tuple[None, None]:
    """
    Returns (signal_type, option_side) or (None, None)

    signal_type: LONG_BUILDUP | SHORT_COVERING | SHORT_BUILDUP | LONG_UNWINDING
    option_side: CALL | PUT
    """
    if ref is None:
        # no 1-min history yet — use raw OI chg sign
        ref_ce, ref_pe = 0.0, 0.0
    else:
        ref_ce, ref_pe = ref

    ce_chg_rising = ce_oi_chg_now > ref_ce
    pe_chg_rising = pe_oi_chg_now > ref_pe

    if pct >= config.MIN_MOVE_PCT:          # price UP
        if ce_chg_rising:
            return "LONG_BUILDUP", "CALL"
        else:
            return "SHORT_COVERING", "CALL"
    elif pct <= -config.MIN_MOVE_PCT:       # price DOWN
        if pe_chg_rising:
            return "SHORT_BUILDUP", "PUT"
        else:
            return "LONG_UNWINDING", "PUT"

    return None, None

def _is_institutional(ce_oi_chg: float, pe_oi_chg: float,
                      total_oi: float, volume: int, prev_volume: int) -> bool:
    """OI change >= 15% of total OI AND today volume >= 1.9x prev day volume."""
    if total_oi <= 0 or prev_volume <= 0:
        return False
    oi_chg_pct = abs(ce_oi_chg + pe_oi_chg) / total_oi * 100
    vol_ratio  = volume / prev_volume if prev_volume > 0 else 0
    return oi_chg_pct >= 15 and vol_ratio >= 1.9

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

    async def _scan_cycle(self):
        movers = await asyncio.to_thread(self.nse.get_fo_movers, config.MIN_MOVE_PCT)
        movers = movers[:config.MAX_STOCKS_PER_RUN]
        log.info(f"Movers >{config.MIN_MOVE_PCT}%: {len(movers)}")

        tasks = [self._process_stock(s) for s in movers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_stock(self, stock: dict):
        sym = stock["symbol"]
        pct = stock["pct"]
        ltp = stock["ltp"]

        try:
            # ── if already signalled — send tracking update ──
            if sym in _active_signals:
                await self._send_tracking(sym, stock)
                return

            # ── cooldown check ───────────────────────────────
            if _on_cooldown(sym):
                return

            # ── fetch chain ──────────────────────────────────
            chain = await asyncio.to_thread(self.nse.get_option_chain, sym)
            if not chain:
                return
            result = await asyncio.to_thread(self.nse.find_top_otm, chain, ltp, config.TOP_N_OTM)
            if not result or (not result["ce_top"] and not result["pe_top"]):
                return

            ce_oi     = sum(o["oi"]     for o in result["ce_top"])
            pe_oi     = sum(o["oi"]     for o in result["pe_top"])
            ce_oi_chg = sum(o["oi_chg"] for o in result["ce_top"])
            pe_oi_chg = sum(o["oi_chg"] for o in result["pe_top"])
            total_oi  = ce_oi + pe_oi

            # record for 1-min comparison
            _record_oi_chg(sym, ce_oi_chg, pe_oi_chg)
            ref = _get_ref_oi_chg(sym)

            # ── classify signal ──────────────────────────────
            signal_type, option_side = _classify_signal(pct, ce_oi_chg, pe_oi_chg, ref)
            if not signal_type:
                return

            # ── OI dominance filter ──────────────────────────
            if option_side == "CALL" and ce_oi <= pe_oi:
                log.info(f"[{sym}] {signal_type} skipped — CE OI ({ce_oi:,}) <= PE OI ({pe_oi:,})")
                return
            if option_side == "PUT" and pe_oi <= ce_oi:
                log.info(f"[{sym}] {signal_type} skipped — PE OI ({pe_oi:,}) <= CE OI ({ce_oi:,})")
                return

            # ── institutional conviction ─────────────────────
            institutional = _is_institutional(
                ce_oi_chg, pe_oi_chg, total_oi,
                stock.get("volume", 0), stock.get("prev_volume", 0)
            )

            # ── pick best option for tracking ────────────────
            top_opts = result["ce_top"] if option_side == "CALL" else result["pe_top"]
            best_opt = top_opts[0] if top_opts else None
            if not best_opt:
                return

            # lot size from config or default
            lot_size = getattr(config, "LOT_SIZE_MAP", {}).get(sym, 1)

            # store active signal
            _active_signals[sym] = {
                "signal_type":    signal_type,
                "option_side":    option_side,
                "strike":         best_opt["strike"],
                "expiry":         best_opt.get("expiry", result["expiry"]),
                "entry_premium":  best_opt["premium"],
                "last_premium":   best_opt["premium"],
                "entry_ltp":      ltp,
                "lot_size":       lot_size,
                "institutional":  institutional,
                "ce_oi_chg":      ce_oi_chg,
                "pe_oi_chg":      pe_oi_chg,
            }

            result["signal_type"]   = signal_type
            result["option_side"]   = option_side
            result["institutional"] = institutional
            result["ce_oi_chg"]     = ce_oi_chg
            result["pe_oi_chg"]     = pe_oi_chg
            result["ce_oi"]         = ce_oi
            result["pe_oi"]         = pe_oi

            msg = build_alert(stock, result)
            console_print(stock, result)
            await self.send(msg, stock)
            _set_cooldown(sym)
            log.info(f"[{sym}] ✅ {signal_type} ({option_side}) fired | institutional={institutional}")

        except Exception as e:
            log.error(f"[{sym}] error: {e}")

    async def _send_tracking(self, sym: str, stock: dict):
        """Send price update for already-alerted stock."""
        sig = _active_signals[sym]
        try:
            # fetch latest premium for the option
            chain = await asyncio.to_thread(self.nse.get_option_chain, sym)
            if not chain:
                return
            result = await asyncio.to_thread(self.nse.find_top_otm, chain, stock["ltp"], config.TOP_N_OTM)
            if not result:
                return

            side_key  = "ce_top" if sig["option_side"] == "CALL" else "pe_top"
            opts      = result.get(side_key, [])
            # find matching strike
            match = next((o for o in opts if o["strike"] == sig["strike"]), None)
            if not match:
                return

            curr_prem      = match["premium"]
            entry_prem     = sig["entry_premium"]
            lot_size       = sig["lot_size"]
            pnl            = (curr_prem - entry_prem) * lot_size
            prem_pct       = (curr_prem - entry_prem) / entry_prem * 100 if entry_prem else 0

            # only send update if premium moved meaningfully (>2%)
            if abs(prem_pct) < 2:
                return

            sig["last_premium"] = curr_prem

            msg = build_tracking_update(
                sym        = sym,
                strike     = sig["strike"],
                option_side= sig["option_side"],
                entry_prem = entry_prem,
                curr_prem  = curr_prem,
                pnl        = pnl,
                lot_size   = lot_size,
                signal_type= sig["signal_type"],
            )
            await self.send(msg, stock)
            log.info(f"[{sym}] 📊 Tracking update | prem {entry_prem}→{curr_prem} | PnL ₹{pnl:,.0f}")

        except Exception as e:
            log.error(f"[{sym}] tracking error: {e}")
