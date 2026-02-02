# app/mcp/prompts/prompt_manager.py
"""
Prompt Manager
==============
Quản lý tất cả system prompts với version control.
Cho phép:
- Load prompts từ files
- Dynamic variable substitution
- Version control và A/B testing
- Template inheritance
"""

from typing import Dict, Optional, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
import json
from string import Template

from app.core.logging import logger


@dataclass
class PromptTemplate:
    """
    A single prompt template.

    Attributes:
        name: Unique template name
        content: Template content with ${variable} placeholders
        version: Template version
        description: What this prompt is for
        variables: List of expected variables
    """
    name: str
    content: str
    version: str = "1.0"
    description: str = ""
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, **kwargs) -> str:
        """
        Render template with variables.

        Args:
            **kwargs: Variables to substitute

        Returns:
            Rendered prompt string
        """
        template = Template(self.content)
        return template.safe_substitute(**kwargs)


class PromptManager:
    """
    Central manager for all prompts.

    Features:
    - Load prompts from directory structure
    - Version management
    - Dynamic rendering with context
    - Fallback to default versions

    Directory structure:
        prompts/
        ├── system/
        │   ├── agent_base.txt
        │   └── task_assistant.txt
        ├── tools/
        │   └── tool_selection.txt
        └── responses/
            └── error_messages.json

    Usage:
        pm = PromptManager()
        await pm.load_prompts("/path/to/prompts")

        # Get and render a prompt
        prompt = pm.get("agent_base", version="1.0")
        rendered = pm.render("agent_base", today=today, tools=tools_list)
    """

    def __init__(self):
        self._templates: Dict[str, Dict[str, PromptTemplate]] = {}  # name -> version -> template
        self._default_versions: Dict[str, str] = {}  # name -> default version
        self._loaded = False

    def register(self, template: PromptTemplate, set_default: bool = True) -> None:
        """
        Register a prompt template.

        Args:
            template: PromptTemplate to register
            set_default: Whether to set as default version
        """
        if template.name not in self._templates:
            self._templates[template.name] = {}

        self._templates[template.name][template.version] = template

        if set_default:
            self._default_versions[template.name] = template.version

        logger.debug(f"Registered prompt: {template.name} v{template.version}")

    def get(
        self,
        name: str,
        version: Optional[str] = None
    ) -> Optional[PromptTemplate]:
        """
        Get a prompt template.

        Args:
            name: Template name
            version: Specific version (optional, uses default)

        Returns:
            PromptTemplate or None if not found
        """
        if name not in self._templates:
            return None

        version = version or self._default_versions.get(name)
        if not version:
            return None

        return self._templates[name].get(version)

    def render(
        self,
        name: str,
        version: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        Get and render a prompt template.

        Args:
            name: Template name
            version: Specific version (optional)
            **kwargs: Variables for template

        Returns:
            Rendered prompt string or None
        """
        template = self.get(name, version)
        if not template:
            logger.warning(f"Prompt template not found: {name}")
            return None

        return template.render(**kwargs)

    def list_templates(self) -> List[Dict[str, Any]]:
        """List all registered templates"""
        result = []
        for name, versions in self._templates.items():
            for version, template in versions.items():
                result.append({
                    "name": name,
                    "version": version,
                    "description": template.description,
                    "is_default": self._default_versions.get(name) == version
                })
        return result

    def set_default_version(self, name: str, version: str) -> bool:
        """Set default version for a template"""
        if name in self._templates and version in self._templates[name]:
            self._default_versions[name] = version
            return True
        return False

    async def load_from_directory(self, base_path: str) -> int:
        """
        Load prompts from directory structure.

        Supports:
        - .txt files: Plain text templates
        - .json files: Structured templates with metadata

        Returns:
            Number of templates loaded
        """
        base = Path(base_path)
        if not base.exists():
            logger.warning(f"Prompts directory not found: {base_path}")
            return 0

        count = 0

        # Load .txt files
        for txt_file in base.rglob("*.txt"):
            try:
                content = txt_file.read_text(encoding="utf-8")
                name = txt_file.stem
                template = PromptTemplate(
                    name=name,
                    content=content,
                    description=f"Loaded from {txt_file.relative_to(base)}"
                )
                self.register(template)
                count += 1
            except Exception as e:
                logger.error(f"Error loading prompt {txt_file}: {e}")

        # Load .json files
        for json_file in base.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Single template
                    template = PromptTemplate(**data)
                    self.register(template)
                    count += 1
                elif isinstance(data, list):
                    # Multiple templates
                    for item in data:
                        template = PromptTemplate(**item)
                        self.register(template)
                        count += 1
            except Exception as e:
                logger.error(f"Error loading prompt {json_file}: {e}")

        self._loaded = True
        logger.info(f"Loaded {count} prompt templates from {base_path}")
        return count

    def register_builtin_prompts(self) -> None:
        """Register built-in default prompts"""

        # Agent base system prompt
        agent_base = PromptTemplate(
            name="agent_system",
            version="1.0",
            description="Base system prompt for the AI agent",
            content="""Bạn là một AI assistant thông minh, hỗ trợ người dùng quản lý công việc và thông tin.

### THÔNG TIN NGỮ CẢNH ###
- Hôm nay là: ${today}
- User ID: ${user_id}

### CÔNG CỤ HIỆN CÓ ###
Bạn có thể sử dụng các tools sau để thực hiện yêu cầu của người dùng:

${tools_description}

### HƯỚNG DẪN ###
1. Phân tích yêu cầu của người dùng
2. Chọn tool phù hợp để thực hiện
3. Nếu cần nhiều bước, thực hiện tuần tự
4. Trả lời bằng ngôn ngữ tự nhiên, thân thiện

### QUY TẮC ###
- Luôn xác nhận trước khi thực hiện hành động quan trọng
- Nếu không chắc chắn, hãy hỏi lại người dùng
- Trả lời ngắn gọn, súc tích
""",
            variables=["today", "user_id", "tools_description"]
        )
        self.register(agent_base)

        # Date parsing context
        date_context = PromptTemplate(
            name="date_context",
            version="1.0",
            description="Context for date parsing",
            content="""### QUY TẮC PHÂN TÍCH NGÀY THÁNG ###
Khi người dùng đề cập đến ngày tháng, áp dụng các quy tắc sau:

1. **Ngày tương đối:**
   - "hôm nay" -> ${today}
   - "ngày mai" -> ${tomorrow}
   - "X ngày nữa" -> Cộng X ngày vào hôm nay

2. **Thứ trong tuần:**
   - Nếu thứ đó chưa qua trong tuần này -> tuần hiện tại
   - Nếu thứ đó đã qua -> tuần kế tiếp

3. **Cụm từ "Tuần sau":**
   - "thứ X tuần sau" -> tuần kế tiếp
   - Ví dụ: "thứ 2 tuần sau" là ${next_monday}

4. **Cụm từ "Tuần sau nữa":**
   - "thứ X tuần sau nữa" -> tuần sau "tuần sau"
""",
            variables=["today", "tomorrow", "next_monday"]
        )
        self.register(date_context)

        # Task context
        task_context = PromptTemplate(
            name="task_context",
            version="1.0",
            description="Context for task operations",
            content="""### NGỮ CẢNH CÔNG VIỆC ###
${priority_context}

### DANH SÁCH CÔNG VIỆC HIỆN CÓ ###
${tasks_json}
""",
            variables=["priority_context", "tasks_json"]
        )
        self.register(task_context)

        # Error messages
        error_messages = PromptTemplate(
            name="error_messages",
            version="1.0",
            description="Standard error messages",
            content=json.dumps({
                "connection_error": "Rất tiếc, tôi không thể kết nối đến hệ thống lúc này. 🛠️",
                "not_found": "Không tìm thấy ${item_type} với ID ${item_id}.",
                "invalid_input": "Thông tin không hợp lệ. Vui lòng kiểm tra lại.",
                "unknown_intent": "Tôi không hiểu yêu cầu của bạn. Bạn có thể diễn đạt lại không?",
                "tool_error": "Có lỗi xảy ra khi thực hiện: ${error_message}"
            }, ensure_ascii=False)
        )
        self.register(error_messages)

        logger.info("Registered built-in prompts")

    def get_error_message(self, key: str, **kwargs) -> str:
        """Get formatted error message"""
        template = self.get("error_messages")
        if not template:
            return f"Error: {key}"

        try:
            messages = json.loads(template.content)
            message = messages.get(key, f"Error: {key}")
            return Template(message).safe_substitute(**kwargs)
        except:
            return f"Error: {key}"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def count(self) -> int:
        return sum(len(versions) for versions in self._templates.values())


# Global singleton
prompt_manager = PromptManager()
