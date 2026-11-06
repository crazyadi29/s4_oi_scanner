# ─────────────────────────────────────────────
#  GAMMA BLAST tag (15-min TF) — tag only, never blocks a signal
# ─────────────────────────────────────────────
import time, logging
from datetime import datetime, timedelta

log = logging.getLogger("gamma")

NEAR_PCT      = 1.0   # within 1% of 15m swing high/low = "near"
LOOKBACK_DAYS = 5
BUILDUP_X     = 3.0   # heavy strike OI >= 3x avg of remaining strikes (mandatory)
NEAR_STRIKES  = 3     # ATM + up to 3 OTM strikes considered "nearby"
VOL_X         = 1.5   # last 15m candle volume >= 1.5x avg of prior candles


def _candles(fyers, symbol: str, oi: bool = False):
    end = datetime.now()
    data = {"symbol": symbol, "resolution": "15", "date_format": "1",
            "range_from": (end - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
            "range_to": end.strftime("%Y-%m-%d"), "cont_flag": "1"}
    if oi:
        data["oi_flag"] = "1"
    time.sleep(0.3)
    r = fyers.history(data)
    if r.get("s") == "ok" or r.get("code") == 200:
        return r.get("candles", [])
    return []


def _volume_good(c) -> bool:
    # c: [ts,o,h,l,c,v,(oi)]
    if len(c) < 6:
        return False
    cur = c[-2][5] if len(c) > 2 else c[-1][5]   # last completed candle
    prev = [x[5] for x in c[:-2]][-20:]
    if not prev:
        return False
    avg = sum(prev) / len(prev)
    return avg > 0 and cur >= VOL_X * avg


def evaluate(fyers, sym: str, ltp: float, chain: dict, atm: float) -> dict | None:
    """Returns dict(pct, score, side, strike, flags) or None if not a gamma blast."""
    try:
        # 1) near resistance / support on underlying 15m
        cs = _candles(fyers, f"NSE:{sym}-EQ")
        if len(cs) < 20:
            return None
        hist = cs[:-1]
        res = max(x[2] for x in hist)
        sup = min(x[3] for x in hist)
        d_res = (res - ltp) / ltp * 100
        d_sup = (ltp - sup) / ltp * 100
        near_res = 0 <= d_res <= NEAR_PCT or ltp > res and (ltp - res) / ltp * 100 <= 0.3
        near_sup = 0 <= d_sup <= NEAR_PCT or ltp < sup and (sup - ltp) / ltp * 100 <= 0.3
        if not (near_res or near_sup):
            return None
        side = "CE" if (near_res and (not near_sup or d_res <= d_sup)) else "PE"
        level = res if side == "CE" else sup

        # 2) OI buildup: heavy strike near ATM/OTM vs the rest (MANDATORY)
        opts = chain.get("data", {}).get("optionsChain", [])
        rows = [o for o in opts if o.get("option_type") == side and o.get("strike_price", 0) > 0]
        if side == "CE":
            near = sorted([o for o in rows if o["strike_price"] >= atm], key=lambda o: o["strike_price"])[:NEAR_STRIKES + 1]
        else:
            near = sorted([o for o in rows if o["strike_price"] <= atm], key=lambda o: -o["strike_price"])[:NEAR_STRIKES + 1]
        if not near:
            return None
        heavy = max(near, key=lambda o: o.get("oi", 0))
        rest = [o.get("oi", 0) for o in rows if o is not heavy]
        avg_rest = sum(rest) / len(rest) if rest else 0
        ratio = heavy.get("oi", 0) / avg_rest if avg_rest > 0 else 0
        if ratio < BUILDUP_X:
            return None   # mandatory condition failed

        flags = {"level": True, "buildup": True, "volume": False, "oi_falling": False}

        # 3 & 4) heavy strike's own 15m chart: volume + OI trend
        oc = _candles(fyers, heavy["symbol"], oi=True)
        if oc:
            flags["volume"] = _volume_good(oc)
            if flags["volume"] is False and heavy.get("volume", 0) <= 0:
                pass
            if len(oc[0]) >= 7 and len(oc) >= 3:
                flags["oi_falling"] = oc[-1][6] < oc[-2][6] and _volume_good(oc)

        score = sum(flags.values())
        if score < 2:
            return None
        return {"pct": {2: 50, 3: 75, 4: 100}[score], "score": score, "side": side,
                "strike": heavy["strike_price"], "ratio": ratio, "level": level, "flags": flags}
    except Exception as e:
        log.warning(f"[{sym}] gamma eval failed: {e}")
        return None
