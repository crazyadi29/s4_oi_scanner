#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  S4 — Fyers Daily Login
#  Run this every morning before market opens:
#    python3 login.py
# ─────────────────────────────────────────────

import webbrowser
from fyers_apiv3 import fyersModel
import config

def main():
    session = fyersModel.SessionModel(
        client_id    = config.FYERS_CLIENT_ID,
        redirect_uri = config.FYERS_REDIRECT_URI,
        response_type= "code",
        state        = "state",
        secret_key   = config.FYERS_SECRET_KEY,
        grant_type   = "authorization_code"
    )
    url = session.generate_authcode()
    print("\n🔗 Opening Fyers login in browser ...")
    print(f"   If browser doesn't open, visit:\n   {url}\n")
    webbrowser.open(url)

    auth_code = input("📋 Paste the auth_code from the redirect URL: ").strip()

    session.set_token(auth_code)
    resp = session.generate_token()

    if resp.get("code") == 200:
        token = f"{config.FYERS_CLIENT_ID}:{resp['access_token']}"
        with open("token.txt", "w") as f:
            f.write(token)
        print("✅ Token saved! You can now run: python3 main.py")
    else:
        print(f"❌ Token generation failed: {resp}")

if __name__ == "__main__":
    main()
