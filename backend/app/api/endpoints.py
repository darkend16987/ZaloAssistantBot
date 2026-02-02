# app/api/endpoints.py
from quart import Blueprint, request, jsonify, current_app
from app.core.logging import logger
from app.core.sessions import get_active_session_count
from app.services import task_flows, scheduler_tasks, oneoffice
from app.services.gemini import gemini_model
from app.core.settings import settings

api_bp = Blueprint('api', __name__)

@api_bp.route('/process_message', methods=['POST'])
async def handle_api_request():
    """Main endpoint to process user messages."""
    try:
        data = await request.get_json()
        user_id, user_message = data.get("user_id"), data.get("message")
        if not user_message or not user_id:
            return jsonify({"error": "Missing user_id or message"}), 400

        logger.info(f"Received request from user_id: {user_id} with message: '{user_message}'")

        # Check if using MCP Agent mode
        if settings.USE_MCP_AGENT:
            # Use new MCP Agent with Gemini Function Calling
            from app.mcp.core.agent import agent
            response = await agent.process_message(user_id, user_message)
            reply_text = response.message
            if response.tool_calls:
                logger.info(f"[MCP] Tools called: {[t['tool'] for t in response.tool_calls]}")
        else:
            # Legacy mode - use task_flows with JSON parsing
            http_session = current_app.aiohttp_session
            reply_text = await task_flows.process_user_request(user_id, user_message, http_session)

        logger.info(f"Replying to user_id: {user_id}: '{reply_text[:200]}...'")
        return jsonify({"reply": reply_text})
    except Exception as e:
        logger.critical(f"Critical error at endpoint: {e}", exc_info=True)
        return jsonify({"reply": "Xin lỗi, bộ não của tôi đang gặp lỗi hệ thống."}), 500

@api_bp.route('/health', methods=['GET'])
async def health_check():
    """Health check endpoint."""
    if settings.USE_MCP_AGENT:
        # MCP mode health check
        from app.mcp.bootstrap import get_system_status
        from app.mcp.core.provider_registry import provider_registry

        status_info = get_system_status()
        provider_statuses = await provider_registry.health_check_all()

        all_healthy = all(s.value == "healthy" for s in provider_statuses.values())
        status_code = 200 if all_healthy else 503

        return jsonify({
            "status": "healthy" if all_healthy else "degraded",
            "mode": "mcp_agent",
            "providers": {name: s.value for name, s in provider_statuses.items()},
            "tools_count": status_info["tools_count"],
            "active_sessions": get_active_session_count()
        }), status_code
    else:
        # Legacy mode health check
        oneoffice_status = "unhealthy"
        gemini_status = "unhealthy"
        http_session = current_app.aiohttp_session

        try:
            test_data = await oneoffice.get_tasks_data(http_session, filters_override={"limit": 1})
            if test_data is not None:
                oneoffice_status = "healthy"
        except Exception: pass

        try:
            await gemini_model.generate_content_async("test")
            gemini_status = "healthy"
        except Exception: pass

        is_healthy = oneoffice_status == "healthy" and gemini_status == "healthy"
        status_code = 200 if is_healthy else 503

        return jsonify({
            "status": "healthy" if is_healthy else "degraded",
            "mode": "legacy",
            "services": {"oneoffice": oneoffice_status, "gemini": gemini_status},
            "active_sessions": get_active_session_count()
        }), status_code


@api_bp.route('/mcp/status', methods=['GET'])
async def mcp_status():
    """Get MCP system status (only available in MCP mode)."""
    if not settings.USE_MCP_AGENT:
        return jsonify({"error": "MCP mode not enabled"}), 400

    from app.mcp.bootstrap import get_system_status
    from app.mcp.core.tool_registry import tool_registry

    status = get_system_status()

    # Get tool details
    tools = []
    for tool in tool_registry.get_all():
        tools.append({
            "name": tool.name,
            "description": tool.description[:100] + "..." if len(tool.description) > 100 else tool.description,
            "category": tool.category,
            "parameters": [p.name for p in tool.parameters]
        })

    return jsonify({
        "status": status,
        "tools": tools
    }), 200

@api_bp.route('/test-birthday', methods=['GET'])
async def test_birthday_endpoint():
    """Manual test for birthday system."""
    try:
        logger.info("=== STARTING MANUAL BIRTHDAY TEST ===")
        # Test 1: Fetch
        data = await scheduler_tasks.fetch_birthdays_from_sheets()
        if not data: return jsonify({"status": "error", "message": "Failed to fetch data"}), 500
        
        # Test 2: Format
        message = scheduler_tasks.format_birthday_message(data)
        
        return jsonify({
            "status": "success", 
            "employee_count": len(data.get('employees', [])),
            "message_preview": message[:500] + "..." if len(message) > 500 else message,
            "full_data": data
        }), 200
    except Exception as e:
        logger.error(f"Error testing birthday system: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/trigger-birthday-now', methods=['POST'])
async def trigger_birthday_now():
    """Trigger sending birthday Zalo message immediately."""
    try:
        await scheduler_tasks.send_birthday_notifications()
        return jsonify({"status": "success", "message": "Triggered birthday notifications"}), 200
    except Exception as e:
        logger.error(f"Error triggering birthday: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
