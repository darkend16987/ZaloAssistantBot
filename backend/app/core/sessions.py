# app/core/sessions.py
import time
from tinydb import TinyDB, Query
from app.core.settings import settings

# Initialize database
db = TinyDB('sessions.json')
User = Query()

def get_session(user_id: str) -> dict:
    """
    Retrieves user session from database.
    - If exists, updates timestamp and returns.
    - If not, creates new session.
    - Automatically cleans up expired sessions.
    """
    cleanup_expired_sessions()
    result = db.search(User.user_id == user_id)
    
    if not result:
        # Default session structure
        session_data = {
            'user_id': user_id,
            'last_interaction_task_ids': [],
            'pending_tasks_queue': [],
            'timestamp': time.time()
        }
        db.insert(session_data)
        return session_data

    # Update timestamp to extend session handling
    db.update({'timestamp': time.time()}, User.user_id == user_id)
    return result[0]

def update_session(user_id: str, data: dict):
    """
    Updates session data for a user.
    """
    data['timestamp'] = time.time()
    db.update(data, User.user_id == user_id)

def cleanup_expired_sessions():
    """
    Removes expired sessions based on SESSION_TIMEOUT_SECONDS.
    """
    expiration_time = time.time() - settings.SESSION_TIMEOUT_SECONDS
    removed_ids = db.remove(User.timestamp < expiration_time)
    if removed_ids and len(removed_ids) > 0:
        print(f"SESSION_MANAGER: Cleaned up {len(removed_ids)} expired sessions.")

def get_active_session_count() -> int:
    return len(db)
