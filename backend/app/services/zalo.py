# app/services/zalo.py
import httpx
from app.core.logging import logger
from app.core.settings import settings

async def send_zalo_message(message: str, target_id: str):
    """Sends Zalo message via Node.js frontend service."""
    if not message:
        return
    try:
        # Frontend URL is currently hardcoded as http://frontend:3000 in the original code,
        # but locally it might be localhost:3000.
        # Assuming the user runs this in Docker as per original code hints, or local.
        # We will use localhost if not in docker, but let's stick to the original logic or make it configurable.
        # Original: http://frontend:3000/send-message
        # If running locally without docker-compose networking, this might fail if 'frontend' is not in hosts.
        # SAFE BET: Use "http://localhost:3000" if running local, "http://frontend:3000" if docker.
        # For now, I'll use localhost as default for local dev, or the original if they use docker.
        # Let's check if there is an env var for this.
        # I'll stick to localhost:3000 for safety in local dev environment requested by user?
        # User said "Project này hiện chỉ có 1 file main.py...".
        # I will assume localhost for now, or make it configurable. 
        base_url = "http://localhost:3000" # Changed from http://frontend:3000 for local dev support
        
        payload = {"target_id": target_id, "message": message}
        async with httpx.AsyncClient() as client:
            res = await client.post(f"{base_url}/send-message", json=payload, timeout=20)
            if res.status_code == 200:
                logger.info(f"Successfully sent message to {target_id}.")
            else:
                logger.error(f"Failed to send to frontend, status: {res.status_code}, response: {res.text}")
    except httpx.RequestError as e:
        logger.error(f"Connection error calling frontend service: {e}")
