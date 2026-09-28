import time
import pytz
from datetime import datetime
import login

IST = pytz.timezone("Asia/Kolkata")
INTERVAL_SEC = 15 * 60

print("⏰ Cron running - refreshing token every 15 min")

while True:
    now = datetime.now(IST)
    print(f"🚀 Triggering login at {now.strftime('%Y-%m-%d %H:%M:%S')} IST")
    try:
        login.auto_login()
    except Exception as e:
        print(f"❌ auto_login failed: {e}")
    time.sleep(INTERVAL_SEC)
