import os
import logging
import time
from fyers_apiv3 import fyersModel

log = logging.getLogger("fyers")

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.txt")

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
        client_id = full.split(":")[0]
        access_token = full.split(":", 1)[1]
        return client_id, access_token
    except Exception:
        raise RuntimeError("No Fyers token found.")

class NSEClient:
    def __init__(self):
        self._init_fyers()

    def _init_fyers(self):
        client_id, access_token = _load_token()
        self.fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, log_path="")
        self._token = access_token
        log.info("Fyers client ready ✅")

    def _refresh_if_needed(self):
        """Reload token from env var — picks up new token if cron refreshed it."""
        current = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
        # strip client_id prefix if present
        token_part = current.split(":", 1)[1] if ":" in current else current
        if token_part and token_part != self._token:
            log.info("Token changed in env — reinitialising Fyers client ♻️")
            self._init_fyers()

    def get_fo_movers(self, min_pct: float = 1.0) -> list[dict]:
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
        batch_size = 50
        for i in range(0, len(fo_symbols), batch_size):
            batch = fo_symbols[i:i + batch_size]
            try:
                resp = self.fyers.quotes({"symbols": ",".join(batch)})
                if resp.get("code") != 200:
                    log.warning(f"Quotes error: {resp.get('message')}")
                    continue
                for q in resp.get("d", []):
                    v = q.get("v", {})
                    sym = q.get("n", "").replace("NSE:", "").replace("-EQ", "")
                    ltp = v.get("lp", 0)
                    prev = v.get("prev_close_price", 0)
                    if prev and prev > 0:
                        pct = round((ltp - prev) / prev * 100, 2)
                        if abs(pct) >= min_pct and ltp > 0:
                            movers.append({
                                "symbol":      sym,
                                "ltp":         ltp,
                                "pct":         pct,
                                "direction":   "LONG" if pct > 0 else "SHORT",
                                "volume":      v.get("vol_traded_today", v.get("volume", 0)),
                                "prev_volume": v.get("prev_volume", v.get("pdv", 0)),
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
            resp = self.fyers.optionchain({"symbol": f"NSE:{symbol}-EQ", "strikecount": 10, "timestamp": ""})
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
            ce_rows = [o for o in opts if o.get("option_type") == "CE"]
            pe_rows = [o for o in opts if o.get("option_type") == "PE"]
            if not ce_rows and not pe_rows:
                return None
            all_strikes = [o["strike_price"] for o in ce_rows + pe_rows if o.get("strike_price", -1) > 0]
            if not all_strikes:
                return None
            atm_strike = min(all_strikes, key=lambda s: abs(s - ltp))
            ce_otm = [o for o in ce_rows if o.get("strike_price", 0) > atm_strike and o.get("oi", 0) >= 500]
            pe_otm = [o for o in pe_rows if o.get("strike_price", 0) < atm_strike and o.get("oi", 0) >= 500]
            ce_top = sorted(ce_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]
            pe_top = sorted(pe_otm, key=lambda x: x.get("oi", 0), reverse=True)[:top_n]
            return {"expiry": expiry, "atm_strike": atm_strike, "ce_top": [_snap_row(o, expiry) for o in ce_top], "pe_top": [_snap_row(o, expiry) for o in pe_top]}
        except Exception as e:
            log.error(f"find_top_otm: {e}", exc_info=True)
            return None

def _snap_row(opt: dict, expiry: str) -> dict:
    return {"type": opt.get("option_type", ""), "strike": opt.get("strike_price", 0), "expiry": expiry, "oi": opt.get("oi", 0), "oi_chg": opt.get("oiChange", 0), "premium": opt.get("ltp", 0), "delta": opt.get("delta", "—"), "gamma": opt.get("gamma", "—"), "iv": opt.get("iv", "—"), "volume": opt.get("volume", 0)}
