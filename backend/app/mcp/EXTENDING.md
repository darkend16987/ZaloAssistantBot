# Hướng dẫn mở rộng hệ thống MCP

Tài liệu này hướng dẫn cách thêm tools và providers mới vào hệ thống MCP.

## 1. Thêm Tool mới

### Bước 1: Tạo Tool class

```python
# app/mcp/tools/my_custom_tools.py
from typing import List
from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType

class MyCustomTool(BaseTool):
    """Tool description - sẽ được hiển thị cho LLM"""

    @property
    def name(self) -> str:
        return "my_custom_tool"  # Tên unique

    @property
    def description(self) -> str:
        # Mô tả chi tiết để LLM hiểu khi nào cần gọi tool này
        return """Mô tả tool làm gì.
Sử dụng khi người dùng hỏi: "ví dụ câu hỏi"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="param1",
                type=ParameterType.STRING,
                description="Mô tả parameter",
                required=True
            ),
            ToolParameter(
                name="param2",
                type=ParameterType.INTEGER,
                description="Mô tả parameter (optional)",
                required=False,
                default=10
            ),
        ]

    @property
    def category(self) -> str:
        return "custom"  # Category để nhóm tools

    async def execute(self, param1: str, param2: int = 10, **kwargs) -> ToolResult:
        try:
            # Logic xử lý
            result = f"Processed: {param1} with {param2}"

            return ToolResult(
                success=True,
                data=result,
                metadata={"param1": param1}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### Bước 2: Đăng ký Tool

```python
# app/mcp/tools/__init__.py
from app.mcp.tools.my_custom_tools import MyCustomTool

def register_all_tools():
    from app.mcp.core.tool_registry import tool_registry

    # ... existing tools ...

    # Register custom tool
    tool_registry.register(MyCustomTool())
```

---

## 2. Thêm Provider mới (Data Source)

### Ví dụ: Provider kết nối với API

```python
# app/mcp/providers/my_api_provider.py
from typing import Dict, Optional, Any
from app.mcp.providers.custom_api_provider import CustomAPIProvider
from app.mcp.core.base_provider import ProviderConfig

class MyAPIProvider(CustomAPIProvider):
    """Provider kết nối với My API"""

    def __init__(self, api_key: str):
        super().__init__(
            config=ProviderConfig(name="my_api", timeout=15),
            auth_token=api_key
        )

    @property
    def name(self) -> str:
        return "my_api"

    @property
    def base_url(self) -> str:
        return "https://api.myservice.com/v1"

    async def get_data(self, query: str) -> Optional[Dict]:
        """Lấy data từ API"""
        return await self.get("/search", params={"q": query})

    async def create_item(self, data: Dict) -> Optional[Dict]:
        """Tạo item mới"""
        return await self.post("/items", data=data)
```

### Đăng ký Provider

```python
# app/mcp/bootstrap.py
from app.mcp.providers.my_api_provider import MyAPIProvider

async def bootstrap_mcp():
    # ... existing code ...

    # Register custom provider
    provider_registry.register(MyAPIProvider(api_key="your-key"))
```

---

## 3. Thêm RAG Knowledge Base

```python
# app/mcp/providers/company_knowledge_provider.py
from app.mcp.providers.base_knowledge_provider import (
    BaseKnowledgeProvider,
    KnowledgeChunk,
    RetrievalResult,
    RetrievalStrategy
)

class CompanyKnowledgeProvider(BaseKnowledgeProvider):
    """RAG provider cho company knowledge base"""

    def __init__(self, vector_db_client):
        super().__init__(strategy=RetrievalStrategy.SEMANTIC)
        self._db = vector_db_client

    @property
    def name(self) -> str:
        return "company_knowledge"

    async def retrieve(self, query: str, top_k: int = 5, filters=None):
        # Query vector database
        results = await self._db.similarity_search(query, k=top_k)

        chunks = [
            KnowledgeChunk(
                content=r.content,
                source=r.metadata.get("source"),
                metadata=r.metadata,
                score=r.score
            )
            for r in results
        ]

        return RetrievalResult(chunks=chunks, query=query, total_found=len(chunks))

    async def index_document(self, content, source, metadata=None):
        await self._db.add_documents([{
            "content": content,
            "source": source,
            "metadata": metadata or {}
        }])
        return True
```

---

## 4. Tạo Tool sử dụng Provider

```python
# app/mcp/tools/knowledge_tools.py
from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType
from app.mcp.core.provider_registry import provider_registry

class SearchKnowledgeTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def description(self) -> str:
        return """Tìm kiếm thông tin trong knowledge base của công ty.
Sử dụng khi người dùng hỏi về chính sách, quy trình, hoặc thông tin nội bộ."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="Câu hỏi hoặc từ khóa tìm kiếm",
                required=True
            )
        ]

    async def execute(self, query: str, **kwargs) -> ToolResult:
        # Get provider
        provider = provider_registry.get("company_knowledge")
        if not provider:
            return ToolResult(success=False, error="Knowledge provider not available")

        # Search
        result = await provider.retrieve(query, top_k=3)

        if not result.chunks:
            return ToolResult(
                success=True,
                data="Không tìm thấy thông tin liên quan."
            )

        # Format response
        response = "📚 Thông tin tìm được:\n\n"
        for i, chunk in enumerate(result.chunks, 1):
            response += f"**[{i}]** {chunk.source}\n{chunk.content}\n\n"

        return ToolResult(success=True, data=response)
```

---

## 5. Tips & Best Practices

### Tool Descriptions
- Viết mô tả rõ ràng để LLM hiểu **khi nào** cần gọi tool
- Bao gồm ví dụ câu hỏi của user
- Sử dụng tiếng Việt nếu target users là người Việt

### Error Handling
```python
async def execute(self, **kwargs) -> ToolResult:
    try:
        # Main logic
        return ToolResult(success=True, data=result)
    except ProviderUnavailableError:
        return ToolResult(success=False, error="Dịch vụ tạm thời không khả dụng")
    except ValidationError as e:
        return ToolResult(success=False, error=f"Dữ liệu không hợp lệ: {e}")
    except Exception as e:
        logger.error(f"Tool error: {e}", exc_info=True)
        return ToolResult(success=False, error="Có lỗi xảy ra")
```

### Testing Tools
```python
# Test tool independently
tool = MyCustomTool()
result = await tool.execute(param1="test", param2=5)
assert result.success
assert "expected" in result.data
```

### Configuration
- Sử dụng `settings.py` cho API keys và config
- Không hardcode credentials trong code
- Sử dụng environment variables
