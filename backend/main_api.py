# main_api.py
import aiohttp
from quart import Quart
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.logging import logger
from app.api.endpoints import api_bp
from app.services import scheduler_tasks

app = Quart(__name__)
app.register_blueprint(api_bp)

@app.before_serving
async def startup():
    """Initialize resources."""
    app.aiohttp_session = aiohttp.ClientSession()
    logger.info("AIOHTTP ClientSession created.")

    scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    
    # === Scheduled Jobs ===
    
    # 1. Daily Briefing / General Updates
    for hour in [9, 11, 14]:
        scheduler.add_job(
            scheduler_tasks.send_general_task_update, 
            'cron', hour=hour, minute=0, misfire_grace_time=300,
            kwargs={'app_session': app.aiohttp_session} # Pass session
        )
        
    # 2. Daily Wrap-up
    scheduler.add_job(
        scheduler_tasks.send_daily_wrap_up, 
        'cron', hour=16, minute=30, misfire_grace_time=300,
        kwargs={'app_session': app.aiohttp_session}
    )
    
    # 3. Urgent Deadline Reminder
    scheduler.add_job(
        scheduler_tasks.check_deadline_reminders, 
        'interval', minutes=30,
        kwargs={'app_session': app.aiohttp_session}
    )

    # 4. Birthday Notifications
    # Thursday 16:00
    scheduler.add_job(scheduler_tasks.send_birthday_notifications, 'cron', day_of_week='thu', hour=16, minute=0, misfire_grace_time=300)
    # Friday 09:00
    scheduler.add_job(scheduler_tasks.send_birthday_notifications, 'cron', day_of_week='fri', hour=9, minute=0, misfire_grace_time=300)
    # Friday 14:00
    scheduler.add_job(scheduler_tasks.send_birthday_notifications, 'cron', day_of_week='fri', hour=14, minute=0, misfire_grace_time=300)

    scheduler.start()
    app.scheduler = scheduler
    logger.info(f"✅ Scheduler started with {len(scheduler.get_jobs())} jobs.")

@app.after_serving
async def shutdown():
    """Cleanup resources."""
    if hasattr(app, 'scheduler') and app.scheduler.running:
        app.scheduler.shutdown()
        logger.info("Scheduler shutdown.")

    if hasattr(app, 'aiohttp_session') and not app.aiohttp_session.closed:
        await app.aiohttp_session.close()
        logger.info("AIOHTTP ClientSession closed.")

if __name__ == '__main__':
    logger.info("Starting Zalo Bot Backend (Modularized)...")
    app.run(host='0.0.0.0', port=5000, debug=False)