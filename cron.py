import time
import pytz
from datetime import datetime
import login

IST = pytz.timezone("Asia/Kolkata")

TARGET_HOUR   = 8
TARGET_MINUTE = 30

_last_run_date = None  # tracks the date we last ran, prevents double-fire

print("⏰ Cron running - waiting for 8:30 AM IST daily...")

while True:
    now_ist = datetime.now(IST)

    if (now_ist.hour == TARGET_HOUR and
        now_ist.minute == TARGET_MINUTE and
        _last_run_date != now_ist.date()):

        print(f"🚀 Triggering login at {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
        try:
            login.auto_login()
        except Exception as e:
            print(f"❌ auto_login failed: {e}")
        _last_run_date = now_ist.date()

    time.sleep(20)
