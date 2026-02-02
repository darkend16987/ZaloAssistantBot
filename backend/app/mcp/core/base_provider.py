# app/mcp/core/base_provider.py
"""
Base Provider Definition
========================
Providers là các nguồn dữ liệu (data sources) cho tools.
Mỗi provider đại diện cho một external service hoặc data source.

Ví dụ providers:
- OneOfficeProvider: Kết nối 1Office API
- BirthdayProvider: Kết nối Google Sheets
- RAGProvider: Knowledge base với vector search
- DatabaseProvider: Direct database access

Tại sao cần Provider?
- Tách biệt data access logic khỏi tool logic
- Dễ mock/test
- Có thể swap provider mà không ảnh hưởng tools
- Support multiple data sources cho cùng một loại data
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
from enum import Enum
import aiohttp


class ProviderStatus(str, Enum):
    """Provider health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderConfig:
    """
    Configuration for a provider.

    Attributes:
        name: Unique provider name
        enabled: Whether provider is active
        timeout: Request timeout in seconds
        retry_count: Number of retries on failure
        custom_config: Provider-specific configuration
    """
    name: str
    enabled: bool = True
    timeout: int = 15
    retry_count: int = 3
    custom_config: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Base class cho tất cả data providers.

    Một provider phải implement:
    - name property: unique identifier
    - initialize(): setup connections
    - health_check(): verify connectivity
    - shutdown(): cleanup resources

    Example:
        class OneOfficeProvider(BaseProvider):
            @property
            def name(self) -> str:
                return "oneoffice"

            async def initialize(self):
                self._session = aiohttp.ClientSession()

            async def get_tasks(self, filters):
                # API call implementation
                pass
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig(name=self.name)
        self._status = ProviderStatus.UNAVAILABLE
        self._http_session: Optional[aiohttp.ClientSession] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier"""
        pass

    @property
    def status(self) -> ProviderStatus:
        """Current provider health status"""
        return self._status

    @property
    def is_available(self) -> bool:
        """Check if provider is ready to handle requests"""
        return self._status in [ProviderStatus.HEALTHY, ProviderStatus.DEGRADED]

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize provider resources.
        Called once when provider is registered.
        """
        pass

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """
        Check provider connectivity and health.
        Should be called periodically.

        Returns:
            Current ProviderStatus
        """
        pass

    async def shutdown(self) -> None:
        """
        Cleanup provider resources.
        Called when application shuts down.
        """
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        self._status = ProviderStatus.UNAVAILABLE

    def set_http_session(self, session: aiohttp.ClientSession) -> None:
        """
        Set shared HTTP session from outside.
        Useful for sharing sessions across providers.
        """
        self._http_session = session

    async def get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
        return self._http_session

    def __repr__(self) -> str:
        return f"<Provider: {self.name} [{self._status.value}]>"


class CompositeProvider(BaseProvider):
    """
    Provider that combines multiple providers.
    Useful for aggregating data from multiple sources.

    Example:
        # Combine data from 1Office and local database
        composite = CompositeProvider([oneoffice_provider, local_db_provider])
    """

    def __init__(self, providers: List[BaseProvider], name: str = "composite"):
        super().__init__(ProviderConfig(name=name))
        self._providers = providers
        self._provider_map = {p.name: p for p in providers}

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def providers(self) -> Dict[str, BaseProvider]:
        return self._provider_map

    async def initialize(self) -> None:
        """Initialize all child providers"""
        for provider in self._providers:
            await provider.initialize()
        self._status = ProviderStatus.HEALTHY

    async def health_check(self) -> ProviderStatus:
        """
        Aggregate health status from all providers.
        Returns HEALTHY only if all providers are healthy.
        """
        statuses = []
        for provider in self._providers:
            status = await provider.health_check()
            statuses.append(status)

        if all(s == ProviderStatus.HEALTHY for s in statuses):
            self._status = ProviderStatus.HEALTHY
        elif any(s == ProviderStatus.HEALTHY for s in statuses):
            self._status = ProviderStatus.DEGRADED
        else:
            self._status = ProviderStatus.UNAVAILABLE

        return self._status

    async def shutdown(self) -> None:
        """Shutdown all child providers"""
        for provider in self._providers:
            await provider.shutdown()
        await super().shutdown()

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get a specific child provider by name"""
        return self._provider_map.get(name)
