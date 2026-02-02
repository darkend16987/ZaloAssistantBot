# app/mcp/core/provider_registry.py
"""
Provider Registry
=================
Central registry để quản lý tất cả data providers.
Providers được đăng ký tại đây và có thể được inject vào tools.

Features:
- Dynamic provider registration
- Health monitoring
- Lifecycle management (init/shutdown)
- Dependency injection for tools
"""

from typing import Dict, List, Optional, Type
import asyncio
from app.mcp.core.base_provider import BaseProvider, ProviderStatus
from app.core.logging import logger


class ProviderRegistry:
    """
    Central registry cho data providers.

    Usage:
        # Register a provider
        provider_registry.register(OneOfficeProvider())

        # Get provider
        oneoffice = provider_registry.get("oneoffice")

        # Initialize all providers
        await provider_registry.initialize_all()

        # Health check
        statuses = await provider_registry.health_check_all()
    """

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._initialized: bool = False

    def register(self, provider: BaseProvider) -> None:
        """
        Register a provider instance.

        Args:
            provider: BaseProvider instance to register
        """
        if provider.name in self._providers:
            logger.warning(f"Provider '{provider.name}' is being re-registered")

        self._providers[provider.name] = provider
        logger.info(f"Registered provider: {provider.name}")

    def unregister(self, provider_name: str) -> bool:
        """Remove a provider from registry"""
        if provider_name in self._providers:
            self._providers.pop(provider_name)
            logger.info(f"Unregistered provider: {provider_name}")
            return True
        return False

    def get(self, provider_name: str) -> Optional[BaseProvider]:
        """Get provider by name"""
        return self._providers.get(provider_name)

    def get_all(self) -> List[BaseProvider]:
        """Get all registered providers"""
        return list(self._providers.values())

    def get_available(self) -> List[BaseProvider]:
        """Get only available providers"""
        return [p for p in self._providers.values() if p.is_available]

    async def initialize_all(self) -> Dict[str, bool]:
        """
        Initialize all registered providers.

        Returns:
            Dict mapping provider name to initialization success
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                await provider.initialize()
                results[name] = True
                logger.info(f"Initialized provider: {name}")
            except Exception as e:
                results[name] = False
                logger.error(f"Failed to initialize provider {name}: {e}")

        self._initialized = True
        return results

    async def shutdown_all(self) -> None:
        """Shutdown all providers gracefully"""
        for name, provider in self._providers.items():
            try:
                await provider.shutdown()
                logger.info(f"Shutdown provider: {name}")
            except Exception as e:
                logger.error(f"Error shutting down provider {name}: {e}")

        self._initialized = False

    async def health_check_all(self) -> Dict[str, ProviderStatus]:
        """
        Run health checks on all providers.

        Returns:
            Dict mapping provider name to health status
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                status = await provider.health_check()
                results[name] = status
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = ProviderStatus.UNAVAILABLE

        return results

    async def ensure_healthy(self, provider_name: str) -> bool:
        """
        Ensure a specific provider is healthy.
        Tries to reinitialize if unhealthy.

        Returns:
            True if provider is healthy or was successfully reinitialized
        """
        provider = self.get(provider_name)
        if not provider:
            return False

        status = await provider.health_check()
        if status == ProviderStatus.HEALTHY:
            return True

        # Try to reinitialize
        try:
            await provider.initialize()
            new_status = await provider.health_check()
            return new_status == ProviderStatus.HEALTHY
        except Exception as e:
            logger.error(f"Failed to reinitialize provider {provider_name}: {e}")
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if registry has been initialized"""
        return self._initialized

    @property
    def count(self) -> int:
        """Number of registered providers"""
        return len(self._providers)

    def get_status_summary(self) -> Dict[str, str]:
        """Get status summary of all providers"""
        return {name: p.status.value for name, p in self._providers.items()}

    def __contains__(self, provider_name: str) -> bool:
        return provider_name in self._providers

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        available = len(self.get_available())
        return f"<ProviderRegistry: {self.count} providers, {available} available>"


# Global singleton instance
provider_registry = ProviderRegistry()
