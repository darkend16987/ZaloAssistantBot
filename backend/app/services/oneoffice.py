# app/services/oneoffice.py
import json
import aiohttp
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from app.core.settings import settings
from app.core.logging import logger

async def get_tasks_data(session: aiohttp.ClientSession, filters_override: Optional[Dict] = None) -> Optional[Dict]:
    """Retrieve tasks from 1Office safely with timeout."""
    default_filters = {
        "assign_ids": settings.DEFAULT_ASSIGNEE, 
        "status": ["DOING", "PAUSE", "PENDING"]
    }
    final_filters = filters_override if filters_override else default_filters
    
    params = {
        "access_token": settings.ONEOFFICE_TOKEN.get_secret_value(),
        "filters": json.dumps([final_filters])
    }
    base_url = "https://innojsc.1office.vn/api/work/normal/gets"
    
    try:
        async with session.get(base_url, params=params, timeout=15) as response:
            response.raise_for_status()
            return await response.json(content_type=None)
    except Exception as e:
        logger.error(f"Error in get_tasks_data: {e}", exc_info=True)
        return None

async def create_and_start_task(session: aiohttp.ClientSession, title: str, end_plan: str, 
                               assignee_name: str, time_end_plan: Optional[str], 
                               priority: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Create and activate task in 2 steps."""
    base_url = "https://innojsc.1office.vn/api/work/normal"
    params = {"access_token": settings.ONEOFFICE_TOKEN.get_secret_value()}
    
    insert_payload = {
        'title': title,
        'assign_ids': assignee_name,
        'owner_ids': settings.DEFAULT_ASSIGNEE,
        'end_plan': end_plan,
        'progress_type': 'PERCENT'
    }
    
    if time_end_plan:
        insert_payload['time_end_plan'] = time_end_plan
    if priority:
        insert_payload['priority'] = priority

    try:
        # Step 1: Create Task
        async with session.post(f"{base_url}/insert", params=params, 
                               data=insert_payload, timeout=15) as response:
            response.raise_for_status()
            resp_json = await response.json(content_type=None)
            
            if resp_json.get("error"):
                return None, resp_json.get("message")
           
            new_task_id = resp_json.get("newPost", {}).get("ID")
            if not new_task_id:
                return None, "System error: Could not retrieve ID of new task."

        # Step 2: Activate Task
        update_payload = {
            'ID': new_task_id, 
            'status': 'Đang thực hiện', 
            'start_plan': datetime.now().strftime('%d/%m/%Y')
        }
        
        async with session.post(f"{base_url}/update", params=params, 
                               data=update_payload, timeout=15) as update_res:
            update_res.raise_for_status()
            update_json = await update_res.json(content_type=None)
            
            if not update_json.get("error"):
                return new_task_id, None
            else:
                return new_task_id, "Created but failed to activate."
                
    except Exception as e:
        logger.error(f"Error in create_and_start_task: {e}", exc_info=True)
        return None, "System error while creating task."

async def update_task(session: aiohttp.ClientSession, task_id: int, payload: Dict) -> bool:
    """Update a specific task."""
    base_url = "https://innojsc.1office.vn/api/work/normal/update"
    params = {"access_token": settings.ONEOFFICE_TOKEN.get_secret_value()}
    payload['ID'] = task_id
    
    try:
        async with session.post(base_url, params=params, data=payload, timeout=15) as response:
            response.raise_for_status()
            resp_json = await response.json(content_type=None)
            return not resp_json.get("error")
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
        return False

async def batch_update_tasks(session: aiohttp.ClientSession, 
                           task_updates: List[Tuple[int, Dict]]) -> List:
    """Execute multiple updates concurrently."""
    import asyncio
    coroutines = [update_task(session, task_id, payload) for task_id, payload in task_updates]
    return await asyncio.gather(*coroutines, return_exceptions=True)
