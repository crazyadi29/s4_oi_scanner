# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  nse_client.py
# ─────────────────────────────────────────────

import requests
import time
import logging

log = logging.getLogger("nse")

BASE = "https://www.nseindia.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}


class NSEClient:
    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers.update(_HEADERS)
        self._init_cookies()

    # ── session cookies ────────────────────────
    def _init_cookies(self):
        try:
            self.sess.get(BASE, timeout=10)
            time.sleep(0.8)
            self.sess.get(f"{BASE}/option-chain", timeout=10)
            time.sleep(0.5)
            log.info("NSE session ready")
        except Exception as e:
            log.warning(f"Cookie init: {e}")

    def _get(self, url: str, retries: int = 3):
        for attempt in range(retries):
            try:
                r = self.sess.get(url, timeout=12)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log.warning(f"GET [{attempt+1}/{retries}] {url.split('?')[0]}: {e}")
                if attempt == 1:
                    self._init_cookies()   # refresh cookies on 2nd fail
                time.sleep(1.5 * (attempt + 1))
        return None

    # ── movers ─────────────────────────────────
    def get_fo_movers(self, min_pct: float = 1.0) -> list[dict]:
        """F&O stocks with |%change| >= min_pct, sorted by move size."""
        url  = f"{BASE}/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
        data = self._get(url)
        if not data:
            return []

        movers = []
        for row in data.get("data", []):
            sym = row.get("symbol", "")
            pct = row.get("pChange", 0)
            ltp = row.get("lastPrice", 0)
            if not sym or sym in ("NIFTY 50", "NIFTY", "Symbol"):
                continue
            if abs(pct) >= min_pct and ltp > 0:
                movers.append({
                    "symbol":    sym,
                    "ltp":       ltp,
                    "pct":       round(pct, 2),
                    "direction": "LONG" if pct > 0 else "SHORT",
                })

        movers.sort(key=lambda x: abs(x["pct"]), reverse=True)
        return movers

    # ── option chain ───────────────────────────
    def get_option_chain(self, symbol: str) -> dict | None:
        url = f"{BASE}/api/option-chain-equities?symbol={symbol}"
        return self._get(url)

    # ── top-N OTM OI ───────────────────────────
    def find_top_otm(self, chain: dict, ltp: float, top_n: int = 2) -> dict | None:
        """
        Nearest expiry only.
        CE side  : OTM only (strike > ATM), top N by OI.
        PE side  : OTM only (strike < ATM), top N by OI.
        ATM excluded (pure OTM as requested).
        """
        try:
            records      = chain.get("records", {})
            expiry_dates = records.get("expiryDates", [])
            if not expiry_dates:
                return None

            nearest  = expiry_dates[0]
            all_data = records.get("data", [])
            exp_data = [d for d in all_data if d.get("expiryDate") == nearest]
            if not exp_data:
                return None

            # ATM = strike closest to LTP
            strikes    = sorted({d["strikePrice"] for d in exp_data})
            atm_strike = min(strikes, key=lambda s: abs(s - ltp))

            ce_list: list[dict] = []
            pe_list: list[dict] = []

            for row in exp_data:
                sp = row["strikePrice"]

                # OTM CE: strike strictly above ATM
                if sp > atm_strike and "CE" in row:
                    ce_list.append(_snap(row["CE"], sp, "CE", nearest))

                # OTM PE: strike strictly below ATM
                if sp < atm_strike and "PE" in row:
                    pe_list.append(_snap(row["PE"], sp, "PE", nearest))

            # sort by OI descending, take top N
            ce_top = sorted(ce_list, key=lambda x: x["oi"], reverse=True)[:top_n]
            pe_top = sorted(pe_list, key=lambda x: x["oi"], reverse=True)[:top_n]

            return {
                "expiry":     nearest,
                "atm_strike": atm_strike,
                "ce_top":     ce_top,
                "pe_top":     pe_top,
            }

        except Exception as e:
            log.error(f"find_top_otm: {e}")
            return None


# ── helper ─────────────────────────────────────
def _snap(opt: dict, strike: float, opt_type: str, expiry: str) -> dict:
    return {
        "type":    opt_type,
        "strike":  strike,
        "expiry":  expiry,
        "oi":      opt.get("openInterest", 0),
        "oi_chg":  opt.get("changeinOpenInterest", 0),
        "premium": opt.get("lastPrice", 0),
        "delta":   opt.get("delta",  "—"),
        "gamma":   opt.get("gamma",  "—"),
        "iv":      opt.get("impliedVolatility", "—"),
        "volume":  opt.get("totalTradedVolume", 0),
    }
