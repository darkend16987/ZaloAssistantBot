# app/core/logging.py
import logging
from app.core.settings import settings

def setup_logging():
    """
    Configures the root logger for the application.
    """
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot_activity.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    # Return module logger
    return logging.getLogger("zalo_assistant")

logger = setup_logging()
