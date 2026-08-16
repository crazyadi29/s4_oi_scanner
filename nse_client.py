# ─────────────────────────────────────────────
#  S4 — MAX OI BOT  |  nse_client.py
#  WebSocket-based live OI feed
# ─────────────────────────────────────────────

import os
import logging
import time
import threading
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws

log = logging.getLogger("fyers")

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.txt")

# ── symbol format maps ─────────────────────────
# Fyers WS symbol format: "NSE:RELIANCE-EQ" for equity
# For options: "NSE:RELIANCE26AUG1300CE-OPT"

def _load_token() -> tuple[str, str]:
    env_token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
    if env_token:
        if ":" in env_token:
            client_id, access_token = env_token.split(":", 1)
            return client_id.strip(), access_token.strip()
        client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
        if not client_id:
            try:
                import config
                client_id = getattr(config, "FYERS_CLIENT_ID", "")
            except Exception:
                pass
        if not client_id:
            raise RuntimeError("FYERS_ACCESS_TOKEN missing CLIENT_ID prefix.")
        return client_id, env_token
    try:
        with open(TOKEN_FILE) as f:
            full = f.read().strip()
        return full.split(":")[0], full.split(":", 1)[1]
    except Exception:
        raise RuntimeError("No Fyers token found.")


# ── live quote store (updated by WebSocket) ────
# { "NSE:RELIANCE-EQ": { "ltp": 1234, "prev_close": 1200, "volume": 5000, "prev_volume": 4000 } }
_quote_store: dict[str, dict] = {}
_quote_lock  = threading.Lock()

# ── live OI store (updated by WebSocket) ───────
# { "NSE:RELIANCE26AUG1300CE-OPT": { "oi": 50000, "ltp": 12.5 } }
_oi_store: dict[str, dict] = {}
_oi_lock  = threading.Lock()


class NSEClient:
    def __init__(self):
        self._client_id, self._access_token = _load_token()
        self._token = self._access_token

        # REST client (for option chain discovery — strike selection)
        self.fyers = fyersModel.FyersModel(
            client_id=self._client_id,
            token=self._access_token,
            log_path=""
        )

        # WebSocket client
        self._ws         = None
        self._ws_thread  = None
        self._subscribed = set()   # symbols currently subscribed
        self._ws_ready   = False

        log.info("Fyers client ready ✅")

    # ── start WebSocket ────────────────────────
    def start_websocket(self, eq_symbols: list[str]):
        """Start WebSocket and subscribe to equity symbols for live quotes."""
        access_token = f"{self._client_id}:{self._access_token}"

        self._ws = data_ws.FyersDataSocket(
            access_token = access_token,
            log_path     = "",
            litemode     = False,
            on_message   = self._on_message,
            on_error     = self._on_error,
            on_connect   = self._on_connect,
            on_close     = self._on_close,
            reconnect    = True,
            reconnect_retry = 10,
        )

        self._eq_symbols = eq_symbols
        self._ws_thread  = threading.Thread(target=self._ws.connect, daemon=True)
        self._ws_thread.start()
        log.info(f"WebSocket thread started — subscribing to {len(eq_symbols)} symbols")

    def subscribe_options(self, symbols: list[str]):
        """Subscribe to additional option symbols for live OI."""
        new = [s for s in symbols if s not in self._subscribed]
        if not new:
            return
        try:
            self._ws.subscribe(symbols=new, data_type="SymbolUpdate")
            self._subscribed.update(new)
            log.info(f"Subscribed {len(new)} option symbols")
        except Exception as e:
            log.error(f"subscribe_options error: {e}")

    # ── WebSocket callbacks ────────────────────
    def _on_connect(self):
        log.info("WebSocket connected ✅")
        self._ws_ready = True
        # subscribe to all equity symbols on connect
        try:
            self._ws.subscribe(symbols=self._eq_symbols, data_type="SymbolUpdate")
            self._subscribed.update(self._eq_symbols)
            log.info(f"Subscribed {len(self._eq_symbols)} equity symbols")
        except Exception as e:
            log.error(f"WS subscribe error: {e}")

    def _on_message(self, msg):
        """Handle live tick — update quote or OI store."""
        try:
            if not isinstance(msg, dict):
                return
            sym = msg.get("symbol", "")
            if not sym:
                return

            if sym.endswith("-EQ"):
                # equity quote update
                with _quote_lock:
                    _quote_store[sym] = {
                        "ltp":          msg.get("ltp", 0),
                        "prev_close":   msg.get("prev_close_price", msg.get("prev_close", 0)),
                        "volume":       msg.get("vol_traded_today", msg.get("volume", 0)),
                        "prev_volume":  msg.get("prev_volume", 0),
                    }
            elif "-OPT" in sym or sym.endswith("CE") or sym.endswith("PE"):
                # option OI update
                with _oi_lock:
                    _oi_store[sym] = {
                        "oi":      msg.get("oi", msg.get("open_interest", 0)),
                        "ltp":     msg.get("ltp", 0),
                        "volume":  msg.get("vol_traded_today", 0),
                    }
        except Exception as e:
            log.error(f"_on_message error: {e}")

    def _on_error(self, msg):
        log.error(f"WebSocket error: {msg}")

    def _on_close(self, msg):
        log.warning(f"WebSocket closed: {msg}")
        self._ws_ready = False

    # ── token refresh ──────────────────────────
    def _refresh_if_needed(self):
        current = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
        token_part = current.split(":", 1)[1] if ":" in current else current
        if token_part and token_part != self._token:
            log.info("Token changed — reinitialising ♻️")
            self._client_id, self._access_token = _load_token()
            self._token = self._access_token
            self.fyers = fyersModel.FyersModel(
                client_id=self._client_id,
                token=self._access_token,
                log_path=""
            )

    # ── get live movers from quote store ───────
    def get_fo_movers(self, min_pct: float = 1.0) -> list[dict]:
        """Return stocks that moved >= min_pct using live WebSocket quotes."""
        self._refresh_if_needed()
        movers = []
        with _quote_lock:
            for sym, q in _quote_store.items():
                if not sym.endswith("-EQ"):
                    continue
                ltp        = q.get("ltp", 0)
                prev_close = q.get("prev_close", 0)
                if not ltp or not prev_close or prev_close <= 0:
                    continue
                pct = round((ltp - prev_close) / prev_close * 100, 2)
                if abs(pct) >= min_pct:
                    clean_sym = sym.replace("NSE:", "").replace("-EQ", "")
                    movers.append({
                        "symbol":       clean_sym,
                        "ltp":          ltp,
                        "pct":          pct,
                        "direction":    "LONG" if pct > 0 else "SHORT",
                        "volume":       q.get("volume", 0),
                        "prev_volume":  q.get("prev_volume", 0),
                    })

        # fallback to REST if WebSocket not ready yet
        if not movers and not self._ws_ready:
            log.warning("WebSocket not ready — falling back to REST quotes")
            movers = self._get_fo_movers_rest(min_pct)

        movers.sort(key=lambda x: abs(x["pct"]), reverse=True)
        log.info(f"F&O movers >{min_pct}%: {len(movers)}")
        return movers

    def _get_fo_movers_rest(self, min_pct: float) -> list[dict]:
        """Fallback REST-based quote fetch (same as original)."""
        fo_symbols = [
            "NSE:360ONE-EQ","NSE:ABB-EQ","NSE:ABBOTINDIA-EQ","NSE:ABCAPITAL-EQ",
            "NSE:ABFRL-EQ","NSE:ACC-EQ","NSE:ADANIENT-EQ",
            "NSE:ADANIGREEN-EQ","NSE:ADANIPORTS-EQ","NSE:ADANIPOWER-EQ","NSE:ALKEM-EQ",
            "NSE:AMBUJACEM-EQ","NSE:APOLLOHOSP-EQ","NSE:APOLLOTYRE-EQ","NSE:ASHOKLEY-EQ",
            "NSE:ASIANPAINT-EQ","NSE:ASTRAL-EQ","NSE:ATGL-EQ","NSE:AUBANK-EQ",
            "NSE:AUROPHARMA-EQ","NSE:AXISBANK-EQ","NSE:BAJAJ-AUTO-EQ","NSE:BAJAJFINSV-EQ",
            "NSE:BAJFINANCE-EQ","NSE:BALKRISIND-EQ","NSE:BANDHANBNK-EQ","NSE:BANKBARODA-EQ",
            "NSE:BATAINDIA-EQ","NSE:BEL-EQ","NSE:BERGEPAINT-EQ","NSE:BHARTIARTL-EQ",
            "NSE:BHEL-EQ","NSE:BIKAJI-EQ","NSE:BIOCON-EQ","NSE:BPCL-EQ",
            "NSE:BRITANNIA-EQ","NSE:BSE-EQ","NSE:BSOFT-EQ","NSE:CANBK-EQ",
            "NSE:CANFINHOME-EQ","NSE:CEATLTD-EQ","NSE:CHOLAFIN-EQ","NSE:CIPLA-EQ",
            "NSE:COALINDIA-EQ","NSE:COFORGE-EQ","NSE:COLPAL-EQ","NSE:CONCOR-EQ",
            "NSE:CROMPTON-EQ","NSE:CUMMINSIND-EQ","NSE:CYIENT-EQ","NSE:DABUR-EQ",
            "NSE:DALBHARAT-EQ","NSE:DEEPAKNTR-EQ","NSE:DELHIVERY-EQ",
            "NSE:DEVYANI-EQ","NSE:DIXON-EQ","NSE:DLF-EQ","NSE:DMART-EQ",
            "NSE:DRREDDY-EQ","NSE:EICHERMOT-EQ","NSE:ELGIEQUIP-EQ","NSE:EMAMILTD-EQ",
            "NSE:ESCORTS-EQ","NSE:EXIDEIND-EQ","NSE:FEDERALBNK-EQ","NSE:FLUOROCHEM-EQ",
            "NSE:FORTIS-EQ","NSE:GAIL-EQ","NSE:GLENMARK-EQ",
            "NSE:GMRAIRPORT-EQ","NSE:GMRINFRA-EQ","NSE:GNFC-EQ","NSE:GODREJCP-EQ",
            "NSE:GODREJPROP-EQ","NSE:GRANULES-EQ","NSE:GRASIM-EQ",
            "NSE:HAL-EQ","NSE:HAVELLS-EQ","NSE:HCLTECH-EQ","NSE:HDFCAMC-EQ",
            "NSE:HDFCBANK-EQ","NSE:HDFCLIFE-EQ","NSE:HEROMOTOCO-EQ",
            "NSE:HINDALCO-EQ","NSE:HINDCOPPER-EQ","NSE:HINDPETRO-EQ","NSE:HINDUNILVR-EQ",
            "NSE:HUDCO-EQ","NSE:ICICIBANK-EQ","NSE:ICICIGI-EQ","NSE:ICICIPRULI-EQ",
            "NSE:IDFCFIRSTB-EQ","NSE:IEX-EQ","NSE:IGL-EQ","NSE:INDHOTEL-EQ",
            "NSE:INDIAMART-EQ","NSE:INDIGO-EQ","NSE:INDUSINDBK-EQ","NSE:INDUSTOWER-EQ",
            "NSE:INFY-EQ","NSE:IOC-EQ","NSE:IRCTC-EQ",
            "NSE:IRFC-EQ","NSE:ITC-EQ","NSE:JINDALSTEL-EQ","NSE:JKCEMENT-EQ",
            "NSE:JSL-EQ","NSE:JSWENERGY-EQ","NSE:JSWSTEEL-EQ","NSE:JUBLFOOD-EQ",
            "NSE:KALYANKJIL-EQ","NSE:KEI-EQ","NSE:KOTAKBANK-EQ","NSE:KPITTECH-EQ",
            "NSE:LATENTVIEW-EQ","NSE:LAURUSLABS-EQ","NSE:LICHSGFIN-EQ",
            "NSE:LT-EQ","NSE:LTIM-EQ","NSE:LTTS-EQ","NSE:LUPIN-EQ",
            "NSE:M&M-EQ","NSE:MANAPPURAM-EQ","NSE:MARICO-EQ",
            "NSE:MARUTI-EQ","NSE:MAXHEALTH-EQ","NSE:MCX-EQ","NSE:MFSL-EQ",
            "NSE:MGL-EQ","NSE:MOTHERSON-EQ","NSE:MPHASIS-EQ","NSE:MRF-EQ",
            "NSE:MUTHOOTFIN-EQ","NSE:NATCOPHARM-EQ","NSE:NAUKRI-EQ","NSE:NAVINFLUOR-EQ",
            "NSE:NESTLEIND-EQ","NSE:NETWORK18-EQ","NSE:NHPC-EQ","NSE:NMDC-EQ",
            "NSE:NTPC-EQ","NSE:NYKAA-EQ","NSE:OBEROIRLTY-EQ","NSE:OFSS-EQ",
            "NSE:ONGC-EQ","NSE:PAGEIND-EQ","NSE:PAYTM-EQ","NSE:PERSISTENT-EQ",
            "NSE:PETRONET-EQ","NSE:PFC-EQ","NSE:PIDILITIND-EQ","NSE:PIIND-EQ",
            "NSE:PNB-EQ","NSE:POLICYBZR-EQ","NSE:POLYCAB-EQ","NSE:POONAWALLA-EQ",
            "NSE:POWERGRID-EQ","NSE:PRESTIGE-EQ","NSE:PVRINOX-EQ","NSE:RBLBANK-EQ",
            "NSE:RECLTD-EQ","NSE:RELIANCE-EQ","NSE:SAIL-EQ","NSE:SBICARD-EQ",
            "NSE:SBILIFE-EQ","NSE:SBIN-EQ","NSE:SHREECEM-EQ","NSE:SHRIRAMFIN-EQ",
            "NSE:SIEMENS-EQ","NSE:SJVN-EQ","NSE:SOLARINDS-EQ","NSE:SRF-EQ",
            "NSE:SUNPHARMA-EQ","NSE:SUNTV-EQ","NSE:SUPREMEIND-EQ","NSE:SYNGENE-EQ",
            "NSE:TATACHEM-EQ","NSE:TATACOMM-EQ","NSE:TATACONSUM-EQ","NSE:TATAELXSI-EQ",
            "NSE:TATAMOTORS-EQ","NSE:TATAPOWER-EQ","NSE:TATASTEEL-EQ","NSE:TCS-EQ",
            "NSE:TECHM-EQ","NSE:TIINDIA-EQ","NSE:TITAN-EQ","NSE:TORNTPHARM-EQ",
            "NSE:TRENT-EQ","NSE:TVSMOTOR-EQ","NSE:UBL-EQ",
            "NSE:ULTRACEMCO-EQ","NSE:UNIONBANK-EQ","NSE:UPL-EQ","NSE:VEDL-EQ",
            "NSE:VOLTAS-EQ","NSE:WIPRO-EQ","NSE:ZOMATO-EQ","NSE:ZYDUSLIFE-EQ",
            "NSE:PATANJALI-EQ","NSE:MANKIND-EQ","NSE:JSWINFRA-EQ","NSE:RVNL-EQ",
            "NSE:IREDA-EQ","NSE:CAMS-EQ","NSE:ANGELONE-EQ","NSE:CDSL-EQ",
            "NSE:MAZDOCK-EQ","NSE:COCHINSHIP-EQ","NSE:BDL-EQ","NSE:GRSE-EQ",
            "NSE:TITAGARH-EQ","NSE:RITES-EQ","NSE:IRCON-EQ","NSE:NBCC-EQ",
        ]
        movers = []
        for i in range(0, len(fo_symbols), 50):
            batch = fo_symbols[i:i+50]
            try:
                resp = self.fyers.quotes({"symbols": ",".join(batch)})
                if resp.get("code") != 200:
                    continue
                for q in resp.get("d", []):
                    v   = q.get("v", {})
                    sym = q.get("n", "").replace("NSE:", "").replace("-EQ", "")
                    ltp  = v.get("lp", 0)
                    prev = v.get("prev_close_price", 0)
                    if prev and prev > 0:
                        pct = round((ltp - prev) / prev * 100, 2)
                        if abs(pct) >= min_pct and ltp > 0:
                            movers.append({
                                "symbol":      sym,
                                "ltp":         ltp,
                                "pct":         pct,
                                "direction":   "LONG" if pct > 0 else "SHORT",
                                "volume":      v.get("vol_traded_today", 0),
                                "prev_volume": v.get("prev_volume", 0),
                            })
            except Exception as e:
                log.error(f"REST quotes batch error: {e}")
            time.sleep(0.3)
        return movers

    # ── get option chain via REST (for strike discovery) ──
    def get_option_chain(self, symbol: str) -> dict | None:
        try:
            time.sleep(0.3)
            resp = self.fyers.optionchain({
                "symbol": f"NSE:{symbol}-EQ",
                "strikecount": 10,
                "timestamp": ""
            })
            if resp.get("code") == 200:
                return resp
            log.warning(f"Option chain [{symbol}]: {resp.get('message')}")
            return None
        except Exception as e:
            log.error(f"get_option_chain [{symbol}]: {e}")
            return None

    # ── find top OTM strikes + subscribe to WS ────
    def find_top_otm(self, chain: dict, ltp: float, top_n: int = 2) -> dict | None:
        try:
            data  = chain.get("data", {})
            opts  = data.get("optionsChain", [])
            if not opts:
                return None

            expiry_list = data.get("expiryData", [])
            expiry      = expiry_list[0].get("date", "") if expiry_list else ""

            ce_rows = [o for o in opts if o.get("option_type") == "CE"]
            pe_rows = [o for o in opts if o.get("option_type") == "PE"]
            if not ce_rows and not pe_rows:
                return None

            all_strikes = [o["strike_price"] for o in ce_rows + pe_rows if o.get("strike_price", -1) > 0]
            if not all_strikes:
                return None

            atm_strike = min(all_strikes, key=lambda s: abs(s - ltp))

            ce_otm = [o for o in ce_rows if o.get("strike_price", 0) > atm_strike and o.get("oi", 0) >= 200]
            pe_otm = [o for o in pe_rows if o.get("strike_price", 0) < atm_strike and o.get("oi", 0) >= 200]

            ce_top = sorted(ce_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]
            pe_top = sorted(pe_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]

            # build OI change by strike lookup
            ce_oichg_by_strike = {o.get("strike_price"): o.get("oiChange", 0) for o in ce_rows}
            pe_oichg_by_strike = {o.get("strike_price"): o.get("oiChange", 0) for o in pe_rows}

            # subscribe top strikes to WebSocket for live OI
            ws_syms = []
            for o in ce_top + pe_top:
                ws_sym = o.get("symbol", "")
                if ws_sym:
                    ws_syms.append(ws_sym)
            if ws_syms and self._ws_ready:
                self.subscribe_options(ws_syms)

            return {
                "expiry":             expiry,
                "atm_strike":         atm_strike,
                "ce_top":             [_snap_row(o, expiry) for o in ce_top],
                "pe_top":             [_snap_row(o, expiry) for o in pe_top],
                "ce_oichg_by_strike": ce_oichg_by_strike,
                "pe_oichg_by_strike": pe_oichg_by_strike,
            }
        except Exception as e:
            log.error(f"find_top_otm: {e}", exc_info=True)
            return None

    # ── get live OI for a subscribed option symbol ──
    def get_live_oi(self, ws_symbol: str) -> dict | None:
        """Return live OI and LTP from WebSocket store."""
        with _oi_lock:
            return _oi_store.get(ws_symbol)


def _snap_row(opt: dict, expiry: str) -> dict:
    return {
        "type":     opt.get("option_type", ""),
        "strike":   opt.get("strike_price", 0),
        "expiry":   expiry,
        "oi":       opt.get("oi", 0),
        "oi_chg":   opt.get("oiChange", 0),
        "premium":  opt.get("ltp", 0),
        "delta":    opt.get("delta", "—"),
        "gamma":    opt.get("gamma", "—"),
        "iv":       opt.get("iv", "—"),
        "volume":   opt.get("volume", 0),
        "symbol":   opt.get("symbol", ""),  # WS symbol for live tracking
    }
