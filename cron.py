import time
import pytz
from datetime import datetime
import login

IST = pytz.timezone("Asia/Kolkata")
TARGET_HOUR, TARGET_MINUTE = 8, 30   # use 8, 0 for bot2
_last_run_date = None

print("⏰ Cron running - waiting for 8:30 AM IST daily...")

while True:
    now = datetime.now(IST)
    if now.hour == TARGET_HOUR and now.minute == TARGET_MINUTE and _last_run_date != now.date():
        print(f"🚀 Triggering login at {now.strftime('%Y-%m-%d %H:%M:%S')} IST")
        try:
            login.auto_login()
        except Exception as e:
            print(f"❌ auto_login failed: {e}")
        _last_run_date = now.date()
    time.sleep(20)
