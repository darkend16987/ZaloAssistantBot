# app/services/zalo.py
import httpx
from app.core.logging import logger
from app.core.settings import settings

async def send_zalo_message(message: str, target_id: str):
    """Sends Zalo message via Node.js frontend service."""
    if not message:
        return
    try:
        # Use configured frontend URL (default: http://frontend:3000)
        base_url = settings.FRONTEND_SERVICE_URL
        
        payload = {"target_id": target_id, "message": message}
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{base_url}/send-message", json=payload, timeout=20)
            if res.status_code == 200:
                logger.info(f"Successfully sent message to {target_id}.")
            else:
                logger.error(f"Failed to send to frontend, status: {res.status_code}, response: {res.text}")
    except httpx.RequestError as e:
        logger.error(f"Connection error calling frontend service: {e}")
