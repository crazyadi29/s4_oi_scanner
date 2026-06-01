import requests
import pyotp
import base64
import hashlib
import os
from fyers_apiv3 import fyersModel

CLIENT_ID = os.environ["FYERS_CLIENT_ID"]
APP_ID = os.environ["FYERS_APP_ID"]
SECRET_KEY = os.environ["FYERS_SECRET_KEY"]
REDIRECT_URI = os.environ["FYERS_REDIRECT_URI"]
PIN = os.environ["FYERS_PIN"]
TOTP_KEY = os.environ["FYERS_TOTP_KEY"]
RAILWAY_TOKEN = os.environ["RAILWAY_API_TOKEN"]
RAILWAY_PROJECT_ID = os.environ["RAILWAY_PROJECT_ID"]
RAILWAY_SERVICE_ID = os.environ["RAILWAY_SERVICE_ID"]
RAILWAY_ENV_ID = os.environ["RAILWAY_ENVIRONMENT_ID"]

BASE_URL = "https://api-t2.fyers.in/vagator/v2"
BASE_URL_2 = "https://api-t1.fyers.in/api/v3"
URL_SEND_LOGIN_OTP = BASE_URL + "/send_login_otp"
URL_VERIFY_TOTP = BASE_URL + "/verify_otp"
URL_VERIFY_PIN = BASE_URL + "/verify_pin"
URL_TOKEN = BASE_URL_2 + "/token"

def auto_login():
    s = requests.Session()
    r1 = s.post(URL_SEND_LOGIN_OTP, json={"fy_id": CLIENT_ID, "app_id": "2"})
    print(f"Step 1 response: {r1.json()}")
    request_key = r1.json()["request_key"]
    print("Step 1 done")
    totp = pyotp.TOTP(TOTP_KEY).now()
    r2 = s.post(URL_VERIFY_TOTP, json={"request_key": request_key, "otp": totp})
    print(f"Step 2 response: {r2.json()}")
    request_key = r2.json()["request_key"]
    print("Step 2 done")
    r3 = s.post(URL_VERIFY_PIN, json={"request_key": request_key, "identity_type": "pin", "identifier": PIN})
    print(f"Step 3 response: {r3.json()}")
    access_token = r3.json()["data"]["access_token"]
    print("Step 3 done")
    app_id_short = APP_ID.split("-")[0]
    r4 = s.post(URL_TOKEN, json={"fyers_id": CLIENT_ID, "app_id": app_id_short, "redirect_uri": REDIRECT_URI, "appType": "100", "code_challenge": "", "state": "state", "scope": "", "nonce": "", "response_type": "code", "create_cookie": True}, headers={"Authorization": f"Bearer {access_token}"})
    print(f"Step 4 response: {r4.json()}")
    auth_code = r4.json()["Url"].split("auth_code=")[1].split("&")[0]
    print("Step 4 done")
    session = fyersModel.SessionModel(client_id=APP_ID, redirect_uri=REDIRECT_URI, response_type="code", state="state", secret_key=SECRET_KEY, grant_type="authorization_code")
    session.set_token(auth_code)
    resp = session.generate_token()
    if resp.get("code") == 200:
        token = f"{APP_ID}:{resp['access_token']}"
        print("Token generated!")
        update_railway_variable(token)
    else:
        print(f"Failed: {resp}")

def update_railway_variable(token):
    query = """
    mutation upsertVariables($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    variables = {"input": {"projectId": RAILWAY_PROJECT_ID, "serviceId": RAILWAY_SERVICE_ID, "environmentId": RAILWAY_ENV_ID, "variables": {"FYERS_ACCESS_TOKEN": token}}}
    r = requests.post("https://backboard.railway.app/graphql/v2", json={"query": query, "variables": variables}, headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"})
    if r.status_code == 200:
        print("Railway variable updated!")
    else:
        print(f"Railway update failed: {r.text}")

if __name__ == "__main__":
    auto_login()