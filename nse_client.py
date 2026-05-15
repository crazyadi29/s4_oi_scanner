# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  nse_client.py
#  Data source: Fyers API
# ─────────────────────────────────────────────

import os
import logging
import time
from fyers_apiv3 import fyersModel

log = logging.getLogger("fyers")

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.txt")


def _load_token() -> tuple[str, str]:
    """
    Returns (client_id, access_token).

    Priority:
      1. FYERS_ACCESS_TOKEN env var (for Railway deployment)
         Accepts both formats:
           - "CLIENT_ID:ACCESS_TOKEN" (full)
           - "ACCESS_TOKEN" (just the token)
      2. token.txt file (for local dev)
    """
    env_token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
    if env_token:
        if ":" in env_token:
            client_id, access_token = env_token.split(":", 1)
            return client_id.strip(), access_token.strip()
        # Just the access token — use FYERS_CLIENT_ID env var or config
        client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
        if not client_id:
            try:
                import config
                client_id = getattr(config, "FYERS_CLIENT_ID", "")
            except Exception:
                pass
        if not client_id:
            raise RuntimeError(
                "FYERS_ACCESS_TOKEN missing CLIENT_ID prefix.\n"
                "  Either: set FYERS_CLIENT_ID env var too, OR\n"
                "  use full format: FYERS_ACCESS_TOKEN=CLIENT_ID:TOKEN"
            )
        return client_id, env_token

    # Fallback: token.txt file
    try:
        with open(TOKEN_FILE) as f:
            full = f.read().strip()
        client_id    = full.split(":")[0]
        access_token = full.split(":", 1)[1]
        return client_id, access_token
    except Exception:
        raise RuntimeError(
            "No Fyers token found.\n"
            "  Option 1 (Railway): set FYERS_ACCESS_TOKEN env variable\n"
            "  Option 2 (local):   run `python3 login.py` to create token.txt"
        )


class NSEClient:

    def __init__(self):
        client_id, access_token = _load_token()
        self.fyers = fyersModel.FyersModel(
            client_id=client_id,
            token=access_token,
            log_path=""
        )
        log.info("Fyers client ready ✅")

    def get_fo_movers(self, min_pct: float = 1.0) -> list[dict]:
        fo_symbols = [
            "NSE:RELIANCE-EQ","NSE:TCS-EQ","NSE:HDFCBANK-EQ","NSE:INFY-EQ",
            "NSE:ICICIBANK-EQ","NSE:HINDUNILVR-EQ","NSE:SBIN-EQ","NSE:BHARTIARTL-EQ",
            "NSE:ITC-EQ","NSE:KOTAKBANK-EQ","NSE:LT-EQ","NSE:AXISBANK-EQ",
            "NSE:ASIANPAINT-EQ","NSE:MARUTI-EQ","NSE:TITAN-EQ","NSE:SUNPHARMA-EQ",
            "NSE:WIPRO-EQ","NSE:ULTRACEMCO-EQ","NSE:ONGC-EQ","NSE:NTPC-EQ",
            "NSE:POWERGRID-EQ","NSE:TECHM-EQ","NSE:HCLTECH-EQ","NSE:BAJFINANCE-EQ",
            "NSE:BAJAJFINSV-EQ","NSE:DIVISLAB-EQ","NSE:DRREDDY-EQ","NSE:CIPLA-EQ",
            "NSE:EICHERMOT-EQ","NSE:HEROMOTOCO-EQ","NSE:ADANIPORTS-EQ","NSE:TATASTEEL-EQ",
            "NSE:JSWSTEEL-EQ","NSE:HINDALCO-EQ","NSE:COALINDIA-EQ","NSE:BPCL-EQ",
            "NSE:IOC-EQ","NSE:GRASIM-EQ","NSE:INDUSINDBK-EQ","NSE:APOLLOHOSP-EQ",
            "NSE:VEDL-EQ","NSE:ADANIENT-EQ","NSE:TATACONSUM-EQ","NSE:BAJAJ-AUTO-EQ",
            "NSE:BRITANNIA-EQ","NSE:NESTLEIND-EQ","NSE:PIDILITIND-EQ","NSE:SIEMENS-EQ",
            "NSE:BANKBARODA-EQ","NSE:PNB-EQ","NSE:CANBK-EQ","NSE:SAIL-EQ",
            "NSE:NMDC-EQ","NSE:RECLTD-EQ","NSE:PFC-EQ","NSE:HDFCLIFE-EQ",
            "NSE:SBILIFE-EQ","NSE:ICICIPRULI-EQ","NSE:MUTHOOTFIN-EQ","NSE:CHOLAFIN-EQ",
            "NSE:TATACOMM-EQ","NSE:OFSS-EQ","NSE:NAUKRI-EQ","NSE:ZOMATO-EQ",
            "NSE:DMART-EQ","NSE:TRENT-EQ","NSE:JUBLFOOD-EQ","NSE:INDIGO-EQ",
            "NSE:IRCTC-EQ","NSE:DLF-EQ","NSE:GODREJPROP-EQ","NSE:AUROPHARMA-EQ",
            "NSE:BIOCON-EQ","NSE:TORNTPHARM-EQ","NSE:LUPIN-EQ","NSE:HAVELLS-EQ",
            "NSE:DIXON-EQ","NSE:ASHOKLEY-EQ","NSE:TATAMOTORS-EQ","NSE:M&M-EQ",
            "NSE:BALKRISIND-EQ","NSE:MRF-EQ","NSE:APOLLOTYRE-EQ","NSE:TATAPOWER-EQ",
            "NSE:ADANIGREEN-EQ","NSE:OBEROIRLTY-EQ","NSE:PRESTIGE-EQ","NSE:BERGEPAINT-EQ",
            "NSE:VOLTAS-EQ","NSE:CROMPTON-EQ","NSE:ESCORTS-EQ","NSE:CEATLTD-EQ",
            "NSE:ABCAPITAL-EQ","NSE:ICICIGI-EQ","NSE:MOTHERSON-EQ","NSE:ATGL-EQ",
            "NSE:IDFCFIRSTB-EQ","NSE:RBLBANK-EQ","NSE:FEDERALBNK-EQ","NSE:BANDHANBNK-EQ",
            "NSE:AUBANK-EQ","NSE:POLYCAB-EQ","NSE:GMRINFRA-EQ","NSE:FLUOROCHEM-EQ",
        ]

        movers = []
        batch_size = 50
        for i in range(0, len(fo_symbols), batch_size):
            batch = fo_symbols[i:i + batch_size]
            try:
                resp = self.fyers.quotes({"symbols": ",".join(batch)})
                if resp.get("code") != 200:
                    log.warning(f"Quotes error: {resp.get('message')}")
                    continue
                for q in resp.get("d", []):
                    v    = q.get("v", {})
                    sym  = q.get("n", "").replace("NSE:", "").replace("-EQ", "")
                    ltp  = v.get("lp", 0)
                    prev = v.get("prev_close_price", 0)
                    if prev and prev > 0:
                        pct = round((ltp - prev) / prev * 100, 2)
                        if abs(pct) >= min_pct and ltp > 0:
                            movers.append({
                                "symbol":    sym,
                                "ltp":       ltp,
                                "pct":       pct,
                                "direction": "LONG" if pct > 0 else "SHORT",
                            })
            except Exception as e:
                log.error(f"Quotes batch error: {e}")
            time.sleep(0.3)

        movers.sort(key=lambda x: abs(x["pct"]), reverse=True)
        log.info(f"F&O movers >{min_pct}%: {len(movers)}")
        return movers

    def get_option_chain(self, symbol: str) -> dict | None:
        try:
            time.sleep(0.5)
            resp = self.fyers.optionchain({
                "symbol":      f"NSE:{symbol}-EQ",
                "strikecount": 10,
                "timestamp":   ""
            })
            if resp.get("code") == 200:
                return resp
            log.warning(f"Option chain [{symbol}]: {resp.get('message')}")
            return None
        except Exception as e:
            log.error(f"get_option_chain [{symbol}]: {e}")
            return None

    def find_top_otm(self, chain: dict, ltp: float, top_n: int = 2) -> dict | None:
        try:
            data = chain.get("data", {})
            opts = data.get("optionsChain", [])
            if not opts:
                return None

            expiry_list = data.get("expiryData", [])
            expiry = expiry_list[0].get("date", "") if expiry_list else ""

            # filter CE and PE rows only
            ce_rows = [o for o in opts if o.get("option_type") == "CE"]
            pe_rows = [o for o in opts if o.get("option_type") == "PE"]

            if not ce_rows and not pe_rows:
                return None

            # find ATM strike
            all_strikes = [
                o["strike_price"] for o in ce_rows + pe_rows
                if o.get("strike_price", -1) > 0
            ]
            if not all_strikes:
                return None

            atm_strike = min(all_strikes, key=lambda s: abs(s - ltp))

            # OTM only
            ce_otm = [o for o in ce_rows if o.get("strike_price", 0) > atm_strike]
            pe_otm = [o for o in pe_rows if o.get("strike_price", 0) < atm_strike]

            # sort by OI descending
            ce_top = sorted(ce_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]
            pe_top = sorted(pe_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]

            return {
                "expiry":     expiry,
                "atm_strike": atm_strike,
                "ce_top":     [_snap_row(o, expiry) for o in ce_top],
                "pe_top":     [_snap_row(o, expiry) for o in pe_top],
            }

        except Exception as e:
            log.error(f"find_top_otm: {e}", exc_info=True)
            return None


def _snap_row(opt: dict, expiry: str) -> dict:
    return {
        "type":    opt.get("option_type", ""),
        "strike":  opt.get("strike_price", 0),
        "expiry":  expiry,
        "oi":      opt.get("oi",       0),
        "oi_chg":  opt.get("oiChange", 0),
        "premium": opt.get("ltp",      0),
        "delta":   opt.get("delta",    "—"),
        "gamma":   opt.get("gamma",    "—"),
        "iv":      opt.get("iv",       "—"),
        "volume":  opt.get("volume",   0),
    }
