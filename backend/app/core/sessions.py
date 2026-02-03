# app/core/sessions.py
import time
from typing import List, Dict, Optional
from tinydb import TinyDB, Query
from app.core.settings import settings

# Initialize database
db = TinyDB('sessions.json')
User = Query()

# Maximum number of conversation turns to keep (each turn = user + assistant)
MAX_CONVERSATION_HISTORY = 10


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
            'conversation_history': [],  # NEW: Store recent conversation
            'timestamp': time.time()
        }
        db.insert(session_data)
        return session_data

    # Ensure conversation_history exists (for existing sessions)
    session = result[0]
    if 'conversation_history' not in session:
        session['conversation_history'] = []
        db.update({'conversation_history': []}, User.user_id == user_id)

    # Update timestamp to extend session handling
    db.update({'timestamp': time.time()}, User.user_id == user_id)
    return session


def update_session(user_id: str, data: dict):
    """
    Updates session data for a user.
    """
    data['timestamp'] = time.time()
    db.update(data, User.user_id == user_id)


def add_to_conversation_history(
    user_id: str,
    user_message: str,
    assistant_response: str
) -> None:
    """
    Add a conversation turn to history.
    Keeps only the last MAX_CONVERSATION_HISTORY turns.

    Args:
        user_id: User ID
        user_message: The user's message
        assistant_response: The bot's response
    """
    session = get_session(user_id)
    history = session.get('conversation_history', [])

    # Add new turn
    history.append({
        'role': 'user',
        'content': user_message,
        'timestamp': time.time()
    })
    history.append({
        'role': 'assistant',
        'content': assistant_response,
        'timestamp': time.time()
    })

    # Keep only last N turns (each turn = 2 messages)
    max_messages = MAX_CONVERSATION_HISTORY * 2
    if len(history) > max_messages:
        history = history[-max_messages:]

    update_session(user_id, {'conversation_history': history})


def get_conversation_history(user_id: str) -> List[Dict]:
    """
    Get conversation history for a user.

    Returns:
        List of message dicts with 'role' and 'content'
    """
    session = get_session(user_id)
    return session.get('conversation_history', [])


def clear_conversation_history(user_id: str) -> None:
    """Clear conversation history for a user."""
    update_session(user_id, {'conversation_history': []})

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
