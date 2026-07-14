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

# ── OI snapshot cache (5-min window) ──────────
# stores raw CE OI + PE OI every cycle so we can compute change ourselves
# Fyers oiChange field is unreliable (stays 0 early session)
OI_CHG_WINDOW_MINS = 5
_oi_snapshot: dict[str, list[tuple[datetime, float, float]]] = {}

def _record_oi(sym: str, ce_oi: float, pe_oi: float):
    """Record raw OI snapshot every scan cycle."""
    now = datetime.now()
    if sym not in _oi_snapshot:
        _oi_snapshot[sym] = []
    _oi_snapshot[sym].append((now, ce_oi, pe_oi))
    # keep 15 min of history
    cutoff = now - timedelta(minutes=15)
    _oi_snapshot[sym] = [e for e in _oi_snapshot[sym] if e[0] >= cutoff]

def _get_oi_change_vs_5m(sym: str, ce_oi_now: float, pe_oi_now: float) -> tuple[float, float, bool]:
    """
    Compare current OI vs snapshot from ~5 mins ago.
    Returns (ce_oi_chg, pe_oi_chg, has_history)
    ce_oi_chg = ce_oi_now - ce_oi_5m_ago  (positive = OI increased)
    has_history = False if less than 5 mins of data
    """
    history = _oi_snapshot.get(sym, [])
    if not history:
        return 0.0, 0.0, False
    now    = datetime.now()
    cutoff = now - timedelta(minutes=OI_CHG_WINDOW_MINS)
    past   = [e for e in history if e[0] <= cutoff]
    if not past:
        return 0.0, 0.0, False
    ref = min(past, key=lambda e: abs((e[0] - cutoff).total_seconds()))
    _, ref_ce, ref_pe = ref
    return (ce_oi_now - ref_ce), (pe_oi_now - ref_pe), True

# ── active signals tracker ─────────────────────
# { symbol: { "signal_type", "strike", "option_type", "entry_premium",
#             "lot_size", "entry_ltp", "last_premium" } }
_active_signals: dict[str, dict] = {}

# ── signal classification ──────────────────────
def _classify_signal(pct: float, ce_oi_chg: float, pe_oi_chg: float) -> tuple[str, str] | tuple[None, None]:
    """
    Returns (signal_type, option_side) or (None, None)
    ce_oi_chg / pe_oi_chg = OI now minus OI 5 mins ago (computed, not from Fyers field)

    signal_type: LONG_BUILDUP | SHORT_COVERING | SHORT_BUILDUP | LONG_UNWINDING
    option_side: CALL | PUT
    """
    ce_chg_rising = ce_oi_chg > 0   # CE OI increased in last 5 mins
    pe_chg_rising = pe_oi_chg > 0   # PE OI increased in last 5 mins

    if pct >= config.MIN_MOVE_PCT:       # price UP
        if ce_chg_rising:
            return "LONG_BUILDUP", "CALL"
        else:
            return "SHORT_COVERING", "CALL"
    elif pct <= -config.MIN_MOVE_PCT:    # price DOWN
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

        # process in batches of 5 to respect Fyers rate limit
        batch_size = 5
        for i in range(0, len(movers), batch_size):
            batch = movers[i:i + batch_size]
            tasks = [self._process_stock(s) for s in batch]
            await asyncio.gather(*tasks, return_exceptions=True)
            if i + batch_size < len(movers):
                await asyncio.sleep(1)

    async def _process_stock(self, stock: dict):
        sym = stock["symbol"]
        pct = stock["pct"]
        ltp = stock["ltp"]

        try:
            # ── if already signalled — send tracking update ──
            if sym in _active_signals:
                await self._send_tracking(sym, stock)
                return

            # ── fetch chain ──────────────────────────────────
            chain = await asyncio.to_thread(self.nse.get_option_chain, sym)
            if not chain:
                return
            result = await asyncio.to_thread(self.nse.find_top_otm, chain, ltp, config.TOP_N_OTM)
            if not result or (not result["ce_top"] and not result["pe_top"]):
                return

            ce_oi     = sum(o["oi"] for o in result["ce_top"])
            pe_oi     = sum(o["oi"] for o in result["pe_top"])
            total_oi  = ce_oi + pe_oi

            # compute OI change vs 5 mins ago from our own snapshot cache
            # (Fyers oiChange field is 0 early session — unreliable)
            ce_oi_chg, pe_oi_chg, has_history = _get_oi_change_vs_5m(sym, ce_oi, pe_oi)

            # record current OI snapshot for future comparisons
            _record_oi(sym, ce_oi, pe_oi)

            # ── need at least 5 mins of history to compute OI change ──
            if not has_history:
                log.info(f"[{sym}] skipped — building OI history (<5 min)")
                return

            # ── classify signal ──────────────────────────────
            signal_type, option_side = _classify_signal(pct, ce_oi_chg, pe_oi_chg)
            if not signal_type:
                return

            # ── OI dominance: use OI change momentum not absolute OI ──
            # for CALL: CE OI change > PE OI change (CE momentum stronger)
            # for PUT:  PE OI change > CE OI change (PE momentum stronger)
            if option_side == "CALL" and ce_oi_chg <= pe_oi_chg:
                log.info(f"[{sym}] {signal_type} skipped — CE OI chg ({ce_oi_chg:,.0f}) <= PE OI chg ({pe_oi_chg:,.0f})")
                return
            if option_side == "PUT" and pe_oi_chg <= ce_oi_chg:
                log.info(f"[{sym}] {signal_type} skipped — PE OI chg ({pe_oi_chg:,.0f}) <= CE OI chg ({ce_oi_chg:,.0f})")
                return

            # ── OI change >= 15% of respective OI (mandatory) ────────
            if option_side == "CALL":
                oi_chg_pct = (ce_oi_chg / ce_oi * 100) if ce_oi > 0 else 0
                if oi_chg_pct < 15:
                    log.info(f"[{sym}] {signal_type} skipped — CE OI chg {oi_chg_pct:.1f}% < 15%")
                    return
            else:
                oi_chg_pct = (pe_oi_chg / pe_oi * 100) if pe_oi > 0 else 0
                if oi_chg_pct < 15:
                    log.info(f"[{sym}] {signal_type} skipped — PE OI chg {oi_chg_pct:.1f}% < 15%")
                    return

            # ── institutional conviction ─────────────────────
            institutional = _is_institutional(
                ce_oi_chg, pe_oi_chg, total_oi,
                stock.get("volume", 0), stock.get("prev_volume", 0)
            )
            log.info(f"[{sym}] {signal_type} | CE OI chg={ce_oi_chg:,.0f} PE OI chg={pe_oi_chg:,.0f} | oi_chg_pct={oi_chg_pct:.1f}%")

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

            curr_prem  = match["premium"]
            entry_prem = sig["entry_premium"]
            last_prem  = sig["last_premium"]
            lot_size   = sig["lot_size"]
            pnl        = (curr_prem - entry_prem) * lot_size

            # only alert when curr premium >= 5% above last sent premium
            if last_prem <= 0:
                return
            pct_above_last = (curr_prem - last_prem) / last_prem * 100
            if pct_above_last < 10:
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
