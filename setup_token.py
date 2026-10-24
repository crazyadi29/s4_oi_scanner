#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
#  S4 — Fyers Token Setup for Railway
#
#  Run this locally whenever you need a fresh Fyers access token:
#    python3 setup_token.py
#
#  What it does:
#    1. Opens the Fyers login page in your browser
#    2. Asks you to paste the auth_code from the redirect URL
#    3. Exchanges the code for an access token
#    4. Validates the token format  (CLIENT_ID:ACCESS_TOKEN)
#    5. Saves it to token.txt
#    6. Prints clear copy-paste instructions for Railway
# ─────────────────────────────────────────────────────────────────────────────

import re
import sys
import webbrowser

from fyers_apiv3 import fyersModel

import config

# ── helpers ───────────────────────────────────────────────────────────────────

BORDER      = "─" * 60
THIN_BORDER = "·" * 60

# Expected format:  CLIENT_ID:ACCESS_TOKEN
# CLIENT_ID looks like  Q7DD93F3RO-100  (alphanumeric + hyphen + digits)
# ACCESS_TOKEN is a non-empty string with no whitespace
_TOKEN_RE = re.compile(r"^[A-Z0-9]+-\d+:.+$")


def _validate_token(token: str) -> tuple[bool, str]:
    """
    Return (is_valid, reason).
    Checks that the token matches CLIENT_ID:ACCESS_TOKEN format.
    """
    token = token.strip()

    if not token:
        return False, "Token is empty."

    if ":" not in token:
        return False, (
            "Missing colon separator. "
            "Expected format: CLIENT_ID:ACCESS_TOKEN  "
            f"(e.g. {config.FYERS_CLIENT_ID}:abc123...)"
        )

    parts = token.split(":", 1)
    client_id, access_token = parts[0], parts[1]

    if not client_id:
        return False, "CLIENT_ID portion is empty."

    if not access_token:
        return False, "ACCESS_TOKEN portion is empty."

    if client_id != config.FYERS_CLIENT_ID:
        return False, (
            f"CLIENT_ID mismatch: got '{client_id}', "
            f"expected '{config.FYERS_CLIENT_ID}'."
        )

    if not _TOKEN_RE.match(token):
        return False, (
            "Token does not match expected pattern "
            f"(CLIENT_ID:ACCESS_TOKEN). Got: '{token[:40]}...'"
        )

    return True, "OK"


def _print_railway_instructions(token: str) -> None:
    """Print a clear, copy-paste-ready block for Railway setup."""
    print()
    print(BORDER)
    print("  🚂  HOW TO SET THIS TOKEN IN RAILWAY")
    print(BORDER)
    print()
    print("  Option A — Railway Dashboard (easiest)")
    print("  ───────────────────────────────────────")
    print("  1. Open your Railway project")
    print("  2. Click  Variables  in the left sidebar")
    print("  3. Click  + New Variable")
    print("  4. Set:")
    print("       Name  →  FYERS_ACCESS_TOKEN")
    print("       Value →  (paste the token below, exactly as shown)")
    print()
    print("  ┌─ COPY THIS EXACT VALUE ──────────────────────────────┐")
    print(f"  {token}")
    print("  └──────────────────────────────────────────────────────┘")
    print()
    print("  Option B — Railway CLI")
    print("  ───────────────────────────────────────")
    print("  Run this command in your terminal:")
    print()
    print(f'  railway variables set FYERS_ACCESS_TOKEN="{token}"')
    print()
    print(BORDER)
    print("  ⚠️  IMPORTANT NOTES")
    print(THIN_BORDER)
    print("  • Do NOT add quotes around the value in the dashboard.")
    print("  • The token expires daily — re-run this script each morning.")
    print("  • After setting the variable, redeploy your Railway service.")
    print(BORDER)
    print()


# ── main flow ─────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(BORDER)
    print("  🔑  S4 — Fyers Token Setup for Railway")
    print(BORDER)
    print()
    print(f"  Client ID   : {config.FYERS_CLIENT_ID}")
    print(f"  Redirect URI: {config.FYERS_REDIRECT_URI}")
    print()

    # ── Step 1: build auth URL ────────────────────────────────────────────────
    session = fyersModel.SessionModel(
        client_id     = config.FYERS_CLIENT_ID,
        redirect_uri  = config.FYERS_REDIRECT_URI,
        response_type = "code",
        state         = "railway_setup",
        secret_key    = config.FYERS_SECRET_KEY,
        grant_type    = "authorization_code",
    )

    auth_url = session.generate_authcode()

    print("  Step 1 of 3 — Log in to Fyers")
    print(THIN_BORDER)
    print("  Opening Fyers login page in your browser …")
    print()
    print(f"  If the browser does not open, visit this URL manually:")
    print(f"  {auth_url}")
    print()

    webbrowser.open(auth_url)

    # ── Step 2: collect auth_code ─────────────────────────────────────────────
    print("  Step 2 of 3 — Paste the auth_code")
    print(THIN_BORDER)
    print("  After logging in, Fyers redirects you to a URL like:")
    print("  https://trade.fyers.in/...?auth_code=XXXXXXXX&state=...")
    print()

    try:
        raw_code = input("  📋 Paste the auth_code here: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\n  ❌ Cancelled by user.")
        sys.exit(1)

    if not raw_code:
        print("\n  ❌ No auth_code entered. Exiting.")
        sys.exit(1)

    # Strip the full URL if the user accidentally pasted it
    if "auth_code=" in raw_code:
        match = re.search(r"auth_code=([^&]+)", raw_code)
        if match:
            raw_code = match.group(1)
            print(f"  ℹ️  Extracted auth_code from URL: {raw_code}")

    # ── Step 3: exchange for access token ─────────────────────────────────────
    print()
    print("  Step 3 of 3 — Generating access token …")
    print(THIN_BORDER)

    session.set_token(raw_code)
    resp = session.generate_token()

    if resp.get("code") != 200:
        print()
        print("  ❌ Token generation failed.")
        print(f"     Response: {resp}")
        print()
        print("  Common causes:")
        print("  • The auth_code has already been used (each code is one-time).")
        print("  • The auth_code expired (they are valid for ~60 seconds).")
        print("  • Wrong CLIENT_ID or SECRET_KEY in config.py.")
        print()
        sys.exit(1)

    raw_access_token = resp.get("access_token", "")
    token = f"{config.FYERS_CLIENT_ID}:{raw_access_token}"

    # ── Validate format ───────────────────────────────────────────────────────
    is_valid, reason = _validate_token(token)

    if not is_valid:
        print()
        print("  ❌ Token format validation failed.")
        print(f"     Reason : {reason}")
        print(f"     Token  : {token[:60]}{'...' if len(token) > 60 else ''}")
        print()
        print("  The token was NOT saved. Please check your config.py and retry.")
        print()
        sys.exit(1)

    # ── Save to token.txt ─────────────────────────────────────────────────────
    with open("token.txt", "w") as fh:
        fh.write(token)

    print()
    print("  ✅ Token generated and validated successfully!")
    print(f"     Saved to : token.txt")
    print(f"     Format   : CLIENT_ID:ACCESS_TOKEN  ✓")
    print(f"     Preview  : {token[:40]}…")

    # ── Railway instructions ──────────────────────────────────────────────────
    _print_railway_instructions(token)


if __name__ == "__main__":
    main()
