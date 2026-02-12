# app/mcp/core/agent.py
"""
Agent Orchestrator
==================
Brain của hệ thống MCP. Agent điều phối việc:
1. Nhận message từ user
2. Sử dụng LLM để phân tích và chọn tools
3. Thực thi tools
4. Format và trả response

Agent sử dụng Gemini Function Calling thay vì parse JSON thủ công,
giúp việc gọi tools chính xác và đáng tin cậy hơn.
"""

import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from app.mcp.core.tool_registry import ToolRegistry, tool_registry
from app.mcp.core.provider_registry import ProviderRegistry, provider_registry
from app.mcp.core.base_tool import ToolResult
from app.mcp.prompts.prompt_manager import PromptManager, prompt_manager
from app.core.settings import settings
from app.core.sessions import (
    get_session, update_session,
    add_to_conversation_history, get_conversation_history
)
from app.core.logging import logger


@dataclass
class AgentContext:
    """
    Context được truyền qua các bước xử lý.

    Attributes:
        user_id: ID của user
        user_message: Message gốc từ user
        session_data: Session data từ TinyDB
        tasks_context: Danh sách tasks hiện có (cho context)
        last_task_ids: IDs của tasks từ interaction trước
        conversation_history: Lịch sử hội thoại gần đây
    """
    user_id: str
    user_message: str
    session_data: Dict[str, Any] = field(default_factory=dict)
    tasks_context: List[Dict] = field(default_factory=list)
    last_task_ids: List[int] = field(default_factory=list)
    conversation_history: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """
    Response từ Agent.

    Attributes:
        message: Message text trả về user
        success: True nếu xử lý thành công
        tool_calls: Danh sách tools đã được gọi
        affected_task_ids: IDs của tasks bị ảnh hưởng
    """
    message: str
    success: bool = True
    tool_calls: List[Dict] = field(default_factory=list)
    affected_task_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentOrchestrator:
    """
    Main agent orchestrator sử dụng Gemini Function Calling.

    Flow:
    1. Nhận message từ user
    2. Build context (tasks list, session, etc.)
    3. Gọi Gemini với function definitions
    4. Gemini trả về function calls
    5. Execute các tools tương ứng
    6. Aggregate responses và trả về user

    Usage:
        agent = AgentOrchestrator()
        await agent.initialize()

        response = await agent.process_message(
            user_id="123",
            message="tạo task ABC deadline thứ 6"
        )
        print(response.message)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry = tool_registry,
        provider_registry: ProviderRegistry = provider_registry,
        prompt_manager: PromptManager = prompt_manager
    ):
        self._tool_registry = tool_registry
        self._provider_registry = provider_registry
        self._prompt_manager = prompt_manager
        self._model: Optional[genai.GenerativeModel] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize agent with Gemini model and tools"""
        if self._initialized:
            return

        # Configure Gemini
        genai.configure(api_key=settings.GOOGLE_API_KEY.get_secret_value())

        # Create function declarations from tools
        function_declarations = self._create_function_declarations()

        # Create model with tools (use configurable model name)
        self._model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            tools=[Tool(function_declarations=function_declarations)]
        )

        # Register built-in prompts
        self._prompt_manager.register_builtin_prompts()

        self._initialized = True
        logger.info(f"Agent initialized with {len(function_declarations)} tools")

    def _create_function_declarations(self) -> List[FunctionDeclaration]:
        """Convert registered tools to Gemini FunctionDeclarations"""
        declarations = []

        for tool in self._tool_registry.get_all():
            # Build parameters schema
            properties = {}
            required = []

            for param in tool.parameters:
                param_schema = {"type": param.type.value.upper()}

                if param.description:
                    param_schema["description"] = param.description
                if param.enum:
                    param_schema["enum"] = param.enum

                properties[param.name] = param_schema

                if param.required:
                    required.append(param.name)

            # Create function declaration
            declaration = FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters={
                    "type": "OBJECT",
                    "properties": properties,
                    "required": required
                } if properties else None
            )
            declarations.append(declaration)

        return declarations

    def _build_system_prompt(self, context: AgentContext) -> str:
        """Build system prompt with context"""
        today = datetime.now()
        tomorrow = today + timedelta(days=1)

        # Calculate this week (Monday to Sunday)
        this_monday = today - timedelta(days=today.weekday())
        this_sunday = this_monday + timedelta(days=6)

        # Calculate next week
        next_monday = this_monday + timedelta(weeks=1)
        next_sunday = next_monday + timedelta(days=6)

        # Calculate week after next (tuần sau nữa)
        week_after_next_monday = this_monday + timedelta(weeks=2)
        week_after_next_sunday = week_after_next_monday + timedelta(days=6)

        # Calculate specific weekdays for this week and next week
        # weekday(): Monday=0, Tuesday=1, ..., Sunday=6
        # Vietnamese: Thứ 2=Monday, Thứ 3=Tuesday, ..., Chủ nhật=Sunday
        def get_weekday_date(week_start: datetime, vn_weekday: int) -> str:
            """vn_weekday: 2=Thứ 2 (Monday), 3=Thứ 3 (Tuesday), ..., 7=Thứ 7 (Saturday), 8/CN=Chủ nhật"""
            if vn_weekday == 8:  # Chủ nhật
                return (week_start + timedelta(days=6)).strftime('%d/%m/%Y')
            else:  # Thứ 2-7 (Monday-Saturday)
                return (week_start + timedelta(days=vn_weekday - 2)).strftime('%d/%m/%Y')

        # Priority context from last interaction
        priority_context = ""
        if context.last_task_ids and context.tasks_context:
            context_tasks = [
                t for t in context.tasks_context
                if t.get('ID') in context.last_task_ids
            ]
            if context_tasks:
                context_str = "\n".join([
                    f'- ID {t["ID"]}: "{t["title"]}"'
                    for t in context_tasks
                ])
                priority_context = f"""### NGỮ CẢNH ƯU TIÊN ###
Người dùng vừa tương tác với các công việc sau. Nếu họ nói 'việc trên', 'công việc đó', hãy ưu tiên chúng:
{context_str}"""

        # Tasks context
        tasks_summary = []
        for t in context.tasks_context[:50]:  # Limit to 50 tasks
            tasks_summary.append({
                "ID": t.get("ID"),
                "title": t.get("title"),
                "deadline": t.get("end_plan"),
                "status": t.get("status")
            })

        return f"""Bạn là trợ lý AI thông minh giúp quản lý công việc và thông tin.

### THÔNG TIN NGỮ CẢNH ###
- Hôm nay là: {today.strftime('%A, %d/%m/%Y')} (Thứ {today.weekday() + 2 if today.weekday() < 6 else 'CN'})
- User ID: {context.user_id}

### QUY TẮC PHÂN TÍCH NGÀY THÁNG ###
**Ngày cụ thể:**
- "hôm nay" = {today.strftime('%d/%m/%Y')}
- "ngày mai" = {tomorrow.strftime('%d/%m/%Y')}

**TUẦN NÀY** ({this_monday.strftime('%d/%m/%Y')} - {this_sunday.strftime('%d/%m/%Y')}):
- "thứ 2 tuần này" = {get_weekday_date(this_monday, 2)}
- "thứ 3 tuần này" = {get_weekday_date(this_monday, 3)}
- "thứ 4 tuần này" = {get_weekday_date(this_monday, 4)}
- "thứ 5 tuần này" = {get_weekday_date(this_monday, 5)}
- "thứ 6 tuần này" = {get_weekday_date(this_monday, 6)}
- "thứ 7 tuần này" = {get_weekday_date(this_monday, 7)}
- "chủ nhật tuần này" = {get_weekday_date(this_monday, 8)}

**TUẦN SAU** ({next_monday.strftime('%d/%m/%Y')} - {next_sunday.strftime('%d/%m/%Y')}):
- "thứ 2 tuần sau" = {get_weekday_date(next_monday, 2)}
- "thứ 5 tuần sau" = {get_weekday_date(next_monday, 5)}
- "thứ 6 tuần sau" = {get_weekday_date(next_monday, 6)}

**TUẦN SAU NỮA** ({week_after_next_monday.strftime('%d/%m/%Y')} - {week_after_next_sunday.strftime('%d/%m/%Y')}):
- "thứ 2 tuần sau nữa" = {get_weekday_date(week_after_next_monday, 2)}
- "thứ 4 tuần sau nữa" = {get_weekday_date(week_after_next_monday, 4)}
- "thứ 6 tuần sau nữa" = {get_weekday_date(week_after_next_monday, 6)}

**Quy tắc khi user chỉ nói "thứ X" (không nói rõ tuần):**
- Nếu thứ đó CHƯA QUA trong tuần này → tính cho TUẦN NÀY
- Nếu thứ đó ĐÃ QUA → tính cho TUẦN SAU

{priority_context}

### DANH SÁCH CÔNG VIỆC HIỆN CÓ ###
{json.dumps(tasks_summary, ensure_ascii=False, indent=2)}

### HƯỚNG DẪN ###
1. Phân tích yêu cầu của người dùng
2. Gọi tool phù hợp để thực hiện
3. Có thể gọi nhiều tools nếu cần
4. Nếu không hiểu, hãy hỏi lại

### QUAN TRỌNG: MULTI-ACTION REQUESTS ###
Khi user nói "tạo VÀ hoàn thành", "add và done", hoặc kết hợp TẠO + HOÀN THÀNH:
→ SỬ DỤNG tool `create_and_complete_task` (KHÔNG phải create_task rồi update_task_status)

### QUAN TRỌNG: THAM CHIẾU ĐẾN CÔNG VIỆC TRƯỚC ###
Khi user nói "công việc trên", "task đó", "việc đó", "cái này", "hoàn thành nó":
1. Kiểm tra LỊCH SỬ HỘI THOẠI để tìm task_id vừa được đề cập
2. Tìm trong phần "(ID: XXXXX)" từ tin nhắn Assistant trước đó
3. Sử dụng task_id đó cho action tiếp theo

Ví dụ:
- Assistant: "✅ Đã tạo công việc 'ABC' (ID: 162523)"
- User: "Hoàn thành công việc trên"
→ Gọi update_task_status với task_id=162523

### QUAN TRỌNG: HIỂU NGỮ CẢNH HỘI THOẠI ###
Bạn có thể được cung cấp LỊCH SỬ HỘI THOẠI GẦN ĐÂY. Hãy sử dụng nó để:

1. **Nhận biết câu trả lời tiếp nối**: Nếu tin nhắn trước của bạn là MỘT CÂU HỎI, và tin nhắn hiện tại của user là câu trả lời ngắn → đây là TRẢ LỜI CHO CÂU HỎI ĐÓ, không phải yêu cầu mới.

   Ví dụ:
   - Assistant: "Deadline cho task này là khi nào?"
   - User: "hôm nay" → Đây là TRẢ LỜI deadline = hôm nay, KHÔNG phải yêu cầu xem task hôm nay

2. **Khi user trả lời câu hỏi clarification**:
   - Hãy tiếp tục thực hiện hành động ban đầu với thông tin mới
   - Ví dụ: Nếu đang tạo task và hỏi deadline, khi user trả lời → tạo task với deadline đó

3. **Phân biệt yêu cầu mới vs câu trả lời**:
   - Yêu cầu mới: "tạo task ABC", "cho tôi xem danh sách", "sinh nhật tuần này"
   - Câu trả lời: "hôm nay", "ngày mai", "thứ 6", "oke", "được"

### LƯU Ý ###
- Trả lời ngắn gọn, thân thiện
- Đảm bảo chuyển đổi ngày tháng chính xác theo quy tắc
- Nếu task_id không rõ, hãy hỏi lại người dùng
"""

    async def process_message(
        self,
        user_id: str,
        message: str
    ) -> AgentResponse:
        """
        Main entry point để xử lý message từ user.

        Args:
            user_id: User ID
            message: Message từ user

        Returns:
            AgentResponse với message và metadata
        """
        if not self._initialized:
            await self.initialize()

        # Build context
        context = await self._build_context(user_id, message)

        # Check for pending tasks in session (multi-step flow)
        if context.session_data.get('pending_tasks_queue'):
            return await self._handle_pending_task(context)

        # Build system prompt
        system_prompt = self._build_system_prompt(context)

        # Build conversation messages including history
        messages = [system_prompt]

        # Add conversation history for context continuity
        if context.conversation_history:
            messages.append("\n### LỊCH SỬ HỘI THOẠI GẦN ĐÂY ###")
            for msg in context.conversation_history[-6:]:  # Last 3 turns (6 messages)
                role = "User" if msg['role'] == 'user' else "Assistant"
                # Truncate long messages in history
                content = msg['content'][:500] + "..." if len(msg['content']) > 500 else msg['content']
                messages.append(f"{role}: {content}")
            messages.append("### KẾT THÚC LỊCH SỬ ###\n")

        # Add current user message
        messages.append(f"User: {message}")

        try:
            # Call Gemini with function calling
            response = await self._model.generate_content_async(
                messages,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,  # Lower for more consistent tool calls
                )
            )

            # Process response and save to history
            agent_response = await self._process_gemini_response(response, context)

            # Save conversation turn to history
            add_to_conversation_history(
                user_id=context.user_id,
                user_message=message,
                assistant_response=agent_response.message
            )

            return agent_response

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            return AgentResponse(
                message="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn.",
                success=False
            )

    async def _build_context(
        self,
        user_id: str,
        message: str
    ) -> AgentContext:
        """Build agent context with session, tasks data, and conversation history"""
        # Get session
        session_data = get_session(user_id)

        # Get conversation history
        conversation_history = get_conversation_history(user_id)

        # Get tasks for context
        tasks_context = []
        oneoffice = self._provider_registry.get("oneoffice")
        if oneoffice and oneoffice.is_available:
            tasks_data = await oneoffice.get_tasks()
            if tasks_data:
                tasks_context = tasks_data.get("data", [])

        return AgentContext(
            user_id=user_id,
            user_message=message,
            session_data=session_data,
            tasks_context=tasks_context,
            last_task_ids=session_data.get('last_interaction_task_ids', []),
            conversation_history=conversation_history
        )

    async def _process_gemini_response(
        self,
        response,
        context: AgentContext
    ) -> AgentResponse:
        """Process Gemini response and execute function calls"""
        all_responses = []
        all_tool_calls = []
        affected_ids = []

        # Check if response has function calls
        for candidate in response.candidates:
            for part in candidate.content.parts:
                # Handle function call
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name
                    args = dict(fc.args) if fc.args else {}

                    logger.info(f"Executing tool: {tool_name} with args: {args}")

                    # Execute tool
                    result = await self._tool_registry.execute(tool_name, **args)

                    all_tool_calls.append({
                        "tool": tool_name,
                        "args": args,
                        "success": result.success
                    })

                    if result.success:
                        all_responses.append(result.data)
                        if result.metadata.get('task_ids'):
                            affected_ids.extend(result.metadata['task_ids'])
                        if result.metadata.get('new_task_id'):
                            affected_ids.append(result.metadata['new_task_id'])
                        if result.metadata.get('task_id'):
                            affected_ids.append(result.metadata['task_id'])
                    else:
                        all_responses.append(f"❌ {result.error}")

                # Handle text response
                elif hasattr(part, 'text') and part.text:
                    text = part.text.strip()
                    if text:
                        all_responses.append(text)

        # Update session with affected IDs
        if affected_ids:
            update_session(context.user_id, {
                'last_interaction_task_ids': list(set(affected_ids))
            })

        # Combine responses
        final_message = "\n\n".join(filter(None, all_responses))

        if not final_message:
            final_message = "Tôi không hiểu yêu cầu của bạn. Bạn có thể diễn đạt lại không?"

        return AgentResponse(
            message=final_message,
            success=True,
            tool_calls=all_tool_calls,
            affected_task_ids=affected_ids
        )

    async def _handle_pending_task(self, context: AgentContext) -> AgentResponse:
        """Handle multi-step task creation flow"""
        pending_queue = context.session_data.get('pending_tasks_queue', [])

        if not pending_queue:
            return AgentResponse(
                message="Không có task nào đang chờ xử lý.",
                success=True
            )

        # Parse date from user message
        from app.services.gemini import ask_gemini_to_parse_date
        end_plan = await ask_gemini_to_parse_date(context.user_message)

        if not end_plan:
            return AgentResponse(
                message="Tôi không hiểu ngày tháng bạn nói. Vui lòng nhập lại (ví dụ: 'thứ 6', 'ngày mai', '25/01/2025').",
                success=False
            )

        # Get first pending task
        current_task = pending_queue.pop(0)

        # Create task
        result = await self._tool_registry.execute(
            "create_task",
            title=current_task['title'],
            end_plan=end_plan,
            assignee=current_task.get('assignee_name')
        )

        response_parts = []
        if result.success:
            response_parts.append(result.data)
        else:
            response_parts.append(f"❌ Lỗi: {result.error}")

        # Check if more tasks pending
        if pending_queue:
            response_parts.append(
                f"\n\n❓ Tiếp theo, deadline cho '{pending_queue[0]['title']}' là khi nào?"
            )
            update_session(context.user_id, {'pending_tasks_queue': pending_queue})
        else:
            update_session(context.user_id, {'pending_tasks_queue': []})

        new_task_id = result.metadata.get('new_task_id')

        return AgentResponse(
            message="\n".join(response_parts),
            success=result.success,
            affected_task_ids=[new_task_id] if new_task_id else []
        )


# Global agent instance
agent = AgentOrchestrator()
