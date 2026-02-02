# app/mcp/providers/custom_api_provider.py
"""
Custom API Provider
===================
Template provider cho việc kết nối với các external APIs.

Sử dụng class này làm base khi cần:
- Kết nối với API nội bộ công ty
- Tích hợp third-party services
- Aggregating data từ nhiều nguồn

Example use cases:
- HR system API
- CRM API
- ERP API
- Weather API
- News API
"""

from abc import abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import aiohttp

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus
from app.core.logging import logger


@dataclass
class APIEndpoint:
    """
    Definition of an API endpoint.

    Attributes:
        path: URL path (relative to base_url)
        method: HTTP method
        description: What this endpoint does
        params_schema: Expected parameters schema
    """
    path: str
    method: str = "GET"
    description: str = ""
    params_schema: Optional[Dict[str, Any]] = None


class CustomAPIProvider(BaseProvider):
    """
    Base class cho custom API integrations.

    Cung cấp:
    - HTTP client management
    - Authentication handling
    - Request/response processing
    - Error handling với retry

    Example implementation:
        class HRSystemProvider(CustomAPIProvider):
            @property
            def name(self) -> str:
                return "hr_system"

            @property
            def base_url(self) -> str:
                return "https://hr.company.com/api"

            async def get_employees(self, department: str = None):
                params = {"department": department} if department else {}
                return await self.request("GET", "/employees", params=params)

            async def get_employee_by_id(self, employee_id: int):
                return await self.request("GET", f"/employees/{employee_id}")
    """

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        auth_token: Optional[str] = None,
        auth_header: str = "Authorization"
    ):
        super().__init__(config)
        self._auth_token = auth_token
        self._auth_header = auth_header
        self._endpoints: Dict[str, APIEndpoint] = {}

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for all API requests"""
        pass

    @property
    def auth_token(self) -> Optional[str]:
        return self._auth_token

    def set_auth_token(self, token: str) -> None:
        """Update authentication token"""
        self._auth_token = token

    def register_endpoint(self, name: str, endpoint: APIEndpoint) -> None:
        """Register an API endpoint"""
        self._endpoints[name] = endpoint

    async def initialize(self) -> None:
        """Initialize HTTP session"""
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        self._status = ProviderStatus.HEALTHY

    async def health_check(self) -> ProviderStatus:
        """Check API connectivity"""
        try:
            # Try to make a simple request
            await self.request("GET", "/health", ignore_errors=True)
            self._status = ProviderStatus.HEALTHY
        except Exception as e:
            logger.warning(f"Health check failed for {self.name}: {e}")
            self._status = ProviderStatus.DEGRADED

        return self._status

    def _build_headers(self, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self._auth_token:
            headers[self._auth_header] = f"Bearer {self._auth_token}"

        if extra_headers:
            headers.update(extra_headers)

        return headers

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        ignore_errors: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Make an API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: URL path (appended to base_url)
            params: Query parameters
            data: Request body (for POST/PUT)
            headers: Extra headers
            ignore_errors: If True, return None on error instead of raising

        Returns:
            Response data as dict, or None on error
        """
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        request_headers = self._build_headers(headers)

        try:
            session = await self.get_http_session()

            async with session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=data,
                headers=request_headers
            ) as response:
                response.raise_for_status()

                # Try to parse JSON
                try:
                    return await response.json()
                except:
                    return {"raw": await response.text()}

        except aiohttp.ClientError as e:
            logger.error(f"API request failed [{method} {path}]: {e}")
            if ignore_errors:
                return None
            raise

    async def get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Convenience method for GET requests"""
        return await self.request("GET", path, params=params)

    async def post(self, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Convenience method for POST requests"""
        return await self.request("POST", path, data=data)

    async def put(self, path: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Convenience method for PUT requests"""
        return await self.request("PUT", path, data=data)

    async def delete(self, path: str) -> Optional[Dict]:
        """Convenience method for DELETE requests"""
        return await self.request("DELETE", path)


class ExampleWeatherProvider(CustomAPIProvider):
    """
    Example implementation: Weather API provider.

    Demonstrates how to create a custom API provider.
    Replace with actual weather API in production.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            config=ProviderConfig(name="weather", timeout=10),
            auth_token=api_key,
            auth_header="X-API-Key"
        )

    @property
    def name(self) -> str:
        return "weather"

    @property
    def base_url(self) -> str:
        return "https://api.weatherapi.com/v1"

    async def get_current_weather(self, city: str) -> Optional[Dict]:
        """Get current weather for a city"""
        return await self.get("/current.json", params={"q": city})

    async def get_forecast(self, city: str, days: int = 3) -> Optional[Dict]:
        """Get weather forecast"""
        return await self.get("/forecast.json", params={"q": city, "days": days})
