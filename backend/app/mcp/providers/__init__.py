# app/mcp/providers/__init__.py
"""
Data Providers
==============
Providers kết nối với các external data sources.
"""

from app.mcp.providers.oneoffice_provider import OneOfficeProvider
from app.mcp.providers.birthday_provider import BirthdayProvider

__all__ = ['OneOfficeProvider', 'BirthdayProvider']
