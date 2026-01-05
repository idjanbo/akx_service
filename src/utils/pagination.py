"""Pagination utility functions."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


@dataclass
class PaginationParams:
    """Pagination parameters."""

    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        """Calculate offset for SQL query."""
        return (self.page - 1) * self.page_size


@dataclass
class PaginatedResult[T]:
    """Paginated result container."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        import math

        return math.ceil(self.total / self.page_size) if self.total > 0 else 1


async def paginate_query[T](
    db: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> tuple[list[T], int]:
    """Apply pagination to a query and return results with total count.

    Args:
        db: Database session
        query: SQLAlchemy select query
        params: Pagination parameters

    Returns:
        Tuple of (items, total_count)
    """
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply pagination
    paginated_query = query.offset(params.offset).limit(params.page_size)
    result = await db.execute(paginated_query)
    items = list(result.scalars().all())

    return items, total
