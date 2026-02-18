# app/services/memory.py
"""
Memory Service
==============
Tích hợp Mem0 cho long-term memory và semantic search.

Cung cấp:
- Long-term user memory (nhớ thông tin xuyên session)
- Semantic search (tìm memory liên quan theo ngữ nghĩa)
- Graceful degradation (hệ thống vẫn chạy bình thường nếu mem0/Qdrant lỗi)

Mem0 tự động trích xuất FACTS từ hội thoại (không lưu raw messages):
  - "User tên là Nam, phòng Marketing"
  - "User thường tạo task deadline thứ 6"
  - "User đã hỏi về quy định nghỉ phép thai sản"
"""

import asyncio
from typing import List, Dict
from functools import partial

from app.core.settings import settings
from app.core.logging import logger


class MemoryService:
    """
    Wrapper around Mem0 with async support and graceful degradation.

    Mem0 là thư viện synchronous, nên tất cả operations được chạy
    trong executor để không block event loop.

    Nếu Qdrant down hoặc mem0 lỗi → tất cả methods trả về empty
    và hệ thống tiếp tục hoạt động bình thường.
    """

    def __init__(self):
        self._memory = None
        self._initialized = False
        self._available = False

    async def initialize(self) -> bool:
        """
        Initialize mem0 with Gemini + Qdrant configuration.

        Returns:
            True nếu khởi tạo thành công, False nếu không.
        """
        if self._initialized:
            return self._available

        if not settings.MEM0_ENABLED:
            self._initialized = True
            self._available = False
            logger.info("Memory service disabled (MEM0_ENABLED=False)")
            return False

        try:
            from mem0 import Memory

            config = {
                "llm": {
                    "provider": "gemini",
                    "config": {
                        "model": settings.GEMINI_MODEL,
                        "api_key": settings.GOOGLE_API_KEY.get_secret_value(),
                        "temperature": 0.1,
                        "max_tokens": 1500,
                    }
                },
                "embedder": {
                    "provider": "gemini",
                    "config": {
                        "model": "models/text-embedding-004",
                        "api_key": settings.GOOGLE_API_KEY.get_secret_value(),
                    }
                },
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "zalo_bot_memories",
                        "host": settings.QDRANT_HOST,
                        "port": settings.QDRANT_PORT,
                        "embedding_model_dims": 768,
                    }
                },
                "version": "v1.1",
            }

            loop = asyncio.get_event_loop()
            self._memory = await loop.run_in_executor(
                None, partial(Memory.from_config, config)
            )

            self._initialized = True
            self._available = True
            logger.info("Memory service initialized (Mem0 + Qdrant)")
            return True

        except Exception as e:
            self._initialized = True
            self._available = False
            logger.warning(f"Memory service unavailable: {e}")
            return False

    async def add(
        self,
        user_id: str,
        user_message: str,
        assistant_response: str
    ) -> None:
        """
        Store conversation turn in memory.

        Mem0 tự động trích xuất facts từ hội thoại và lưu vào vector store.
        Method này nên được gọi fire-and-forget (asyncio.create_task)
        để không block response trả về user.

        Args:
            user_id: User ID
            user_message: Message gốc từ user
            assistant_response: Response từ bot
        """
        if not self._available:
            return

        try:
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_response},
            ]

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                partial(self._memory.add, messages, user_id=user_id)
            )
            logger.debug(f"Memory stored for user {user_id}")

        except Exception as e:
            logger.warning(f"Failed to store memory: {e}")

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Search relevant memories for the current query.

        Args:
            user_id: User ID
            query: Current user message
            limit: Max number of memories to return

        Returns:
            List of memory dicts with 'memory' and 'score' keys.
            Returns empty list if unavailable or error.
        """
        if not self._available:
            return []

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                partial(self._memory.search, query, user_id=user_id, limit=limit)
            )

            memories = []
            for result in results.get("results", []):
                memory_text = result.get("memory", "")
                if memory_text:
                    memories.append({
                        "memory": memory_text,
                        "score": result.get("score", 0),
                    })

            if memories:
                logger.debug(f"Found {len(memories)} relevant memories for user {user_id}")

            return memories

        except Exception as e:
            logger.warning(f"Failed to search memory: {e}")
            return []

    async def get_all(self, user_id: str) -> List[Dict]:
        """Get all memories for a user."""
        if not self._available:
            return []

        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                partial(self._memory.get_all, user_id=user_id)
            )
            return results.get("results", [])

        except Exception as e:
            logger.warning(f"Failed to get memories: {e}")
            return []

    @property
    def is_available(self) -> bool:
        return self._available


# Global singleton
memory_service = MemoryService()
