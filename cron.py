import schedule
import time
import login

# Every day at 8:30 AM IST = 3:00 AM UTC
schedule.every().day.at("03:00").do(auto_token.auto_login)

print("⏰ Cron running - waiting for 8:30 AM IST daily...")
while True:
    schedule.run_pending()
    time.sleep(30)