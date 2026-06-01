import requests
import pyotp
import base64
import hashlib
import os
from fyers_apiv3 import fyersModel

# All from Railway environment variables
CLIENT_ID    = os.environ["FYERS_CLIENT_ID"]
SECRET_KEY   = os.environ["FYERS_SECRET_KEY"]
REDIRECT_URI = os.environ["FYERS_REDIRECT_URI"]
PIN          = os.environ["FYERS_PIN"]
TOTP_KEY     = os.environ["FYERS_TOTP_KEY"]

RAILWAY_TOKEN      = os.environ["RAILWAY_API_TOKEN"]
RAILWAY_PROJECT_ID = os.environ["RAILWAY_PROJECT_ID"]
RAILWAY_SERVICE_ID = os.environ["RAILWAY_SERVICE_ID"]

def auto_login():
    s = requests.Session()

    # Step 1: Send login ID
    r1 = s.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
    json={"fy_id": CLIENT_ID, "app_id": "2"})
print(f"Step 1 response: {r1.json()}")
request_key = r1.json()["request_key"]
print("✅ Step 1 done - login OTP sent")
    # Step 2: Verify TOTP (auto-generated!)
    totp = pyotp.TOTP(TOTP_KEY).now()
    r2 = s.post("https://api-t2.fyers.in/vagator/v2/verify_otp",
        json={"request_key": request_key, "otp": totp})
    request_key = r2.json()["request_key"]
    print("✅ Step 2 done - TOTP verified")

    # Step 3: Verify PIN
    pin_b64 = base64.b64encode(PIN.encode()).decode()
    r3 = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
        json={"request_key": request_key,
              "identity_type": "pin",
              "identifier": pin_b64})
    print("✅ Step 3 done - PIN verified")

    # Step 4: Get auth code
    app_id_short = CLIENT_ID.split("-")[0]
    r4 = s.post("https://api.fyers.in/api/v2/token",
        json={"fyers_id": CLIENT_ID,
              "app_id": app_id_short,
              "redirect_uri": REDIRECT_URI,
              "appType": "100",
              "code_challenge": "",
              "state": "state",
              "scope": "",
              "nonce": "",
              "response_type": "code",
              "create_cookie": True})
    auth_code = r4.json()["Url"].split("auth_code=")[1].split("&")[0]
    print("✅ Step 4 done - auth code received")

    # Step 5: Generate access token
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        state="state",
        secret_key=SECRET_KEY,
        grant_type="authorization_code"
    )
    session.set_token(auth_code)
    resp = session.generate_token()

    if resp.get("code") == 200:
        token = f"{CLIENT_ID}:{resp['access_token']}"
        print(f"✅ Token generated!")

        # Step 6: Update Railway env variable automatically
        update_railway_variable(token)
    else:
        print(f"❌ Failed: {resp}")

def update_railway_variable(token):
    # Railway GraphQL API to update env variable
    query = """
    mutation upsertVariables($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    variables = {
        "input": {
            "projectId": RAILWAY_PROJECT_ID,
            "serviceId": RAILWAY_SERVICE_ID,
            "environmentId": os.environ["RAILWAY_ENVIRONMENT_ID"],
            "variables": {
                "FYERS_ACCESS_TOKEN": token
            }
        }
    }
    r = requests.post(
        "https://backboard.railway.app/graphql/v2",
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {RAILWAY_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    if r.status_code == 200:
        print("✅ Railway variable updated!")
    else:
        print(f"❌ Railway update failed: {r.text}")

if __name__ == "__main__":
    auto_login()