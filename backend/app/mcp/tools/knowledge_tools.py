# app/mcp/tools/knowledge_tools.py
"""
Knowledge Tools
===============
MCP tools cho việc tra cứu thông tin từ knowledge base.
Bao gồm các quy định, quy chế, nội quy của công ty.
"""

from typing import List, Optional

from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType
from app.mcp.core.provider_registry import provider_registry
from app.mcp.providers.regulations_provider import RegulationsProvider
from app.core.logging import logger


def get_regulations_provider() -> RegulationsProvider:
    """Get Regulations provider from registry"""
    provider = provider_registry.get("regulations")
    if not provider:
        raise RuntimeError("Regulations provider not initialized")
    return provider


class SearchRegulationsTool(BaseTool):
    """Tool để tra cứu các quy định, quy chế, nội quy của công ty"""

    @property
    def name(self) -> str:
        return "search_regulations"

    @property
    def description(self) -> str:
        return """Tra cứu thông tin từ các quy định, quy chế, nội quy của công ty.

SỬ DỤNG KHI người dùng hỏi về:
- Thời gian làm việc, giờ làm việc, đi muộn, về sớm
- Nghỉ phép, phép năm, nghỉ lễ, nghỉ tết
- Nghỉ ốm, thai sản, nghỉ việc riêng
- Quy định về du lịch, hỗ trợ du lịch
- Vay tiền, quỹ hỗ trợ cho vay
- Công tác phí, định mức chi phí
- Phúc lợi: kết hôn, sinh con, ốm đau, hiếu, lễ tết
- Kỷ luật lao động, sa thải
- Tác phong, trang phục làm việc
- Bảo mật thông tin, bảo vệ tài sản

VÍ DỤ:
- "Nghỉ phép được bao nhiêu ngày?" → search_regulations(query="nghỉ phép bao nhiêu ngày")
- "Công ty hỗ trợ đi du lịch bao nhiêu?" → search_regulations(query="hỗ trợ du lịch kinh phí")
- "Chế độ thai sản như thế nào?" → search_regulations(query="nghỉ thai sản chế độ")
- "Vay tiền công ty được bao nhiêu?" → search_regulations(query="vay tiền quỹ hỗ trợ")
- "Công tác phí đi Đà Nẵng là bao nhiêu?" → search_regulations(query="công tác phí khách sạn")"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ParameterType.STRING,
                description="Câu hỏi hoặc từ khóa cần tra cứu. Nên bao gồm các từ khóa chính liên quan đến quy định.",
                required=True
            ),
            ToolParameter(
                name="document_type",
                type=ParameterType.STRING,
                description="Loại văn bản cần tra cứu (optional). Nếu biết rõ loại văn bản, chỉ định để kết quả chính xác hơn.",
                required=False,
                enum=["noi_quy_lao_dong", "quy_che_du_lich", "quy_cho_vay", "dinh_muc_chi"]
            )
        ]

    @property
    def category(self) -> str:
        return "knowledge"

    async def execute(
        self,
        query: str,
        document_type: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_regulations_provider()

            # Build filters if document_type specified
            filters = None
            if document_type:
                filters = {"doc_id": document_type}

            # Get retrieval result - INCREASED to top 3 for better context
            result = await provider.retrieve(query, top_k=3, filters=filters)

            if not result.chunks:
                return ToolResult(
                    success=True,
                    data="Không tìm thấy thông tin liên quan trong các quy định của công ty. Vui lòng liên hệ phòng Hành chính - Nhân sự để được hỗ trợ.",
                    metadata={"found": False, "query": query}
                )

            # Build context for LLM
            context_parts = []
            for i, chunk in enumerate(result.chunks, 1):
                context_parts.append(f"--- ĐOẠN {i} (Nguồn: {chunk.source}) ---\n{chunk.content}")
            
            full_context = "\n\n".join(context_parts)

            # Call Gemini to synthesize answer
            try:
                from app.services.gemini import gemini_model
                
                prompt = f"""
Bạn là trợ lý AI nội bộ của công ty. Nhiệm vụ của bạn là trả lời câu hỏi của nhân viên dựa trên các quy định được cung cấp dưới đây.

### THÔNG TIN QUY ĐỊNH (CONTEXT) ###
{full_context}

### CÂU HỎI CỦA NHÂN VIÊN ###
"{query}"

### YÊU CẦU TRẢ LỜI ###
1.  **Trả lời trực tiếp**: Đi thẳng vào vấn đề, không vòng vo.
2.  **Dựa vào Context**: Chỉ sử dụng thông tin có trong Context trên. Nếu Context không đủ để trả lời, hãy nói rõ là "Thông tin này chưa được quy định rõ trong tài liệu tìm thấy".
3.  **Trích dẫn nguồn**: Cuối câu trả lời, hãy ghi rõ nguồn (ví dụ: Theo Điều X - Quy chế Y).
4.  **Văn phong**: Chuyên nghiệp, thân thiện, súc tích. Dùng định dạng Markdown (bold, list) để dễ đọc.

HÃY TRẢ LỜI NGAY DƯỚI ĐÂY:
"""
                # Call Gemini
                response = await gemini_model.generate_content_async(prompt)
                final_answer = response.text.strip()
                
            except Exception as llm_error:
                logger.error(f"Error calling Gemini for synthesis: {llm_error}")
                # Fallback to raw chunks if LLM fails
                final_answer = "### Thông tin tìm thấy:\n\n" + full_context

            # Build response metadata
            sources = list(set(
                c.metadata.get("doc_id", "unknown")
                for c in result.chunks
            ))

            return ToolResult(
                success=True,
                data=final_answer,
                metadata={
                    "found": True,
                    "query": query,
                    "sources": sources,
                    "chunk_count": len(result.chunks),
                    "total_found": result.total_found,
                    "synthesized": True
                }
            )

        except Exception as e:
            logger.error(f"SearchRegulationsTool error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Lỗi khi tra cứu quy định: {str(e)}"
            )


class ListRegulationsTool(BaseTool):
    """Tool để liệt kê các văn bản quy định hiện có"""

    @property
    def name(self) -> str:
        return "list_regulations"

    @property
    def description(self) -> str:
        return """Liệt kê tất cả các văn bản quy định, quy chế, nội quy hiện có của công ty.

SỬ DỤNG KHI người dùng hỏi:
- "Có những quy định gì?"
- "Liệt kê các quy chế của công ty"
- "Công ty có những văn bản nào?"
"""

    @property
    def parameters(self) -> List[ToolParameter]:
        return []  # No parameters needed

    @property
    def category(self) -> str:
        return "knowledge"

    async def execute(self, **kwargs) -> ToolResult:
        try:
            provider = get_regulations_provider()

            documents = provider.list_documents()

            if not documents:
                return ToolResult(
                    success=True,
                    data="Hiện chưa có văn bản quy định nào trong hệ thống.",
                    metadata={"count": 0}
                )

            # Format list
            lines = ["**Các văn bản quy định của công ty:**\n"]
            for i, doc in enumerate(documents, 1):
                lines.append(f"{i}. **{doc['title']}**")
                if doc.get('description'):
                    lines.append(f"   {doc['description']}")
                lines.append("")

            lines.append(f"\n*Tổng cộng: {len(documents)} văn bản*")
            lines.append("\nĐể tra cứu chi tiết, hãy hỏi về nội dung cụ thể (ví dụ: 'nghỉ phép bao nhiêu ngày?')")

            return ToolResult(
                success=True,
                data="\n".join(lines),
                metadata={
                    "count": len(documents),
                    "documents": [d['id'] for d in documents]
                }
            )

        except Exception as e:
            logger.error(f"ListRegulationsTool error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Lỗi khi liệt kê văn bản: {str(e)}"
            )


# Export tools for registration
__all__ = ['SearchRegulationsTool', 'ListRegulationsTool']
