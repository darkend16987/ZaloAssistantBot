# app/mcp/bootstrap.py
"""
MCP Bootstrap
=============
Khởi tạo toàn bộ hệ thống MCP:
- Đăng ký providers
- Đăng ký tools
- Khởi tạo agent

File này được gọi khi application startup.
"""

from app.mcp.core.tool_registry import tool_registry
from app.mcp.core.provider_registry import provider_registry
from app.mcp.core.mcp_server import mcp_server
from app.mcp.core.agent import agent
from app.mcp.prompts.prompt_manager import prompt_manager

from app.mcp.providers.oneoffice_provider import OneOfficeProvider
from app.mcp.providers.birthday_provider import BirthdayProvider
from app.mcp.providers.enhanced_regulations_provider import EnhancedRegulationsProvider
from app.mcp.tools import register_all_tools

from app.core.logging import logger


async def bootstrap_mcp() -> None:
    """
    Bootstrap toàn bộ hệ thống MCP.

    Được gọi một lần khi application startup.
    Thực hiện theo thứ tự:
    1. Đăng ký providers
    2. Khởi tạo providers
    3. Đăng ký tools
    4. Khởi tạo agent
    5. Khởi tạo MCP server

    Usage:
        # In main_api.py startup
        from app.mcp.bootstrap import bootstrap_mcp
        await bootstrap_mcp()
    """
    logger.info("🚀 Bootstrapping MCP system...")

    # Step 1: Register providers
    logger.info("Registering providers...")
    provider_registry.register(OneOfficeProvider())
    provider_registry.register(BirthdayProvider())
    provider_registry.register(EnhancedRegulationsProvider())

    # Step 2: Initialize providers
    logger.info("Initializing providers...")
    init_results = await provider_registry.initialize_all()
    for name, success in init_results.items():
        status = "✅" if success else "❌"
        logger.info(f"  {status} Provider '{name}': {'initialized' if success else 'failed'}")

    # Step 3: Register tools
    logger.info("Registering tools...")
    register_all_tools()
    logger.info(f"  Registered {len(tool_registry)} tools")

    # Step 4: Register built-in prompts
    logger.info("Registering prompts...")
    prompt_manager.register_builtin_prompts()
    logger.info(f"  Registered {prompt_manager.count} prompts")

    # Step 5: Initialize agent
    logger.info("Initializing agent...")
    await agent.initialize()

    # Step 6: Initialize MCP server
    logger.info("Initializing MCP server...")
    await mcp_server.initialize()

    logger.info("✅ MCP system bootstrapped successfully!")
    logger.info(f"   - Providers: {provider_registry.count}")
    logger.info(f"   - Tools: {tool_registry.count}")
    logger.info(f"   - Prompts: {prompt_manager.count}")


async def shutdown_mcp() -> None:
    """
    Gracefully shutdown MCP system.

    Được gọi khi application shutdown.
    """
    logger.info("Shutting down MCP system...")

    await mcp_server.shutdown()
    await provider_registry.shutdown_all()

    logger.info("MCP system shutdown complete")


def get_system_status() -> dict:
    """Get current MCP system status"""
    return {
        "providers": provider_registry.get_status_summary(),
        "tools_count": tool_registry.count,
        "tools_categories": tool_registry.categories,
        "prompts_count": prompt_manager.count,
        "agent_initialized": agent._initialized,
        "mcp_server_initialized": mcp_server.is_initialized
    }
