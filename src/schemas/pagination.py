"""Custom pagination schema with page/page_size parameters.

This module provides a customized Page class that uses:
- Input params: page, page_size (instead of page, size)
- Output fields: page, page_size (instead of page, size)

Usage:
    from src.schemas.pagination import CustomPage

    @router.get("/items")
    async def list_items() -> CustomPage[ItemResponse]:
        return await apaginate(db, query)
"""

from typing import TypeVar

from fastapi import Query
from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseFieldsAliases, UseParamsFields

__all__ = ["CustomPage"]

T = TypeVar("T")

# Custom Page with page/page_size naming convention
# - Input: ?page=1&page_size=20
# - Output: { "items": [...], "total": 100, "page": 1, "page_size": 20, "pages": 5 }
CustomPage = CustomizedPage[
    Page[T],
    UseParamsFields(
        size=Query(20, ge=1, le=100, alias="page_size", description="Page size"),
    ),
    UseFieldsAliases(
        size="page_size",
    ),
]
