import schedule
import time
import login
 
schedule.every(1).minutes.do(login.auto_login)
print("⏰ Cron running - waiting for 8:30 AM IST daily...")
while True:
    schedule.run_pending()
    time.sleep(30)