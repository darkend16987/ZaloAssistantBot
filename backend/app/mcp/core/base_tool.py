# app/mcp/core/base_tool.py
"""
Base Tool Definition
====================
Định nghĩa cấu trúc chuẩn cho các MCP tools.
Mỗi tool có:
- name: tên unique
- description: mô tả (cho LLM hiểu khi nào cần gọi)
- parameters: schema của input
- execute(): async function thực thi tool
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union
from enum import Enum
import json


class ParameterType(str, Enum):
    """Supported parameter types for tools"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """
    Định nghĩa một parameter của tool.

    Example:
        ToolParameter(
            name="status",
            type=ParameterType.STRING,
            description="Trạng thái công việc",
            required=False,
            enum=["DOING", "COMPLETED", "PAUSE"]
        )
    """
    name: str
    type: ParameterType
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None
    items_type: Optional[ParameterType] = None  # For array types

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format for Gemini function calling"""
        schema = {
            "type": self.type.value,
            "description": self.description
        }

        if self.enum:
            schema["enum"] = self.enum

        if self.type == ParameterType.ARRAY and self.items_type:
            schema["items"] = {"type": self.items_type.value}

        if self.default is not None:
            schema["default"] = self.default

        return schema


@dataclass
class ToolResult:
    """
    Kết quả trả về từ tool execution.

    Attributes:
        success: True nếu tool chạy thành công
        data: Dữ liệu trả về (có thể format cho user)
        error: Error message nếu có lỗi
        metadata: Thông tin bổ sung (task IDs affected, etc.)
    """
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }


class BaseTool(ABC):
    """
    Base class cho tất cả MCP tools.

    Mỗi tool phải implement:
    - name, description, parameters properties
    - execute() async method

    Example:
        class GetTasksTool(BaseTool):
            @property
            def name(self) -> str:
                return "get_tasks"

            @property
            def description(self) -> str:
                return "Lấy danh sách công việc từ 1Office"

            @property
            def parameters(self) -> List[ToolParameter]:
                return [
                    ToolParameter("status", ParameterType.STRING, "Filter by status")
                ]

            async def execute(self, **kwargs) -> ToolResult:
                # Implementation
                pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (used in function calling)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Mô tả tool cho LLM hiểu.
        Nên viết rõ ràng khi nào cần dùng tool này.
        """
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """List of parameters this tool accepts"""
        pass

    @property
    def category(self) -> str:
        """Category for grouping tools (tasks, birthdays, etc.)"""
        return "general"

    @property
    def requires_context(self) -> bool:
        """Whether this tool needs user context (session, user_id)"""
        return False

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Thực thi tool với các parameters.

        Args:
            **kwargs: Parameters được truyền vào (đã validated)

        Returns:
            ToolResult với success/error và data
        """
        pass

    def to_gemini_function(self) -> Dict[str, Any]:
        """
        Convert tool definition to Gemini function calling format.

        Returns:
            Dict compatible with google.generativeai tools parameter
        """
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def to_mcp_schema(self) -> Dict[str, Any]:
        """
        Convert to MCP-compatible schema.
        This format can be used by any MCP-compatible client.
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    param.name: param.to_json_schema()
                    for param in self.parameters
                },
                "required": [p.name for p in self.parameters if p.required]
            }
        }

    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate parameters before execution.

        Returns:
            (is_valid, error_message)
        """
        for param in self.parameters:
            if param.required and param.name not in params:
                return False, f"Missing required parameter: {param.name}"

            if param.name in params and param.enum:
                if params[param.name] not in param.enum:
                    return False, f"Invalid value for {param.name}. Must be one of: {param.enum}"

        return True, None

    async def safe_execute(self, **kwargs) -> ToolResult:
        """
        Execute with validation and error handling.
        """
        is_valid, error = self.validate_params(kwargs)
        if not is_valid:
            return ToolResult(success=False, error=error)

        try:
            return await self.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(e)}"
            )

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
