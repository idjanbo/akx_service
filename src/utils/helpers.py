"""Response model builder utilities."""

from datetime import datetime
from typing import Any


def format_utc_datetime(dt: datetime | None) -> str | None:
    """Format datetime to ISO string with Z suffix for UTC.

    后端存储 UTC 时间（datetime.utcnow()），但 Python 的 isoformat()
    不会添加时区信息。添加 Z 后缀让前端 new Date() 正确识别为 UTC。

    Args:
        dt: datetime object (assumed UTC) or None

    Returns:
        ISO format string with Z suffix (e.g., "2026-01-10T10:30:00Z") or None
    """
    if dt is None:
        return None
    return f"{dt.isoformat()}Z"


def build_lookup_maps(
    db_results: dict[str, list[Any]],
) -> dict[str, dict[int, Any]]:
    """Build ID-to-object lookup maps from database results.

    Args:
        db_results: Dictionary with key names and lists of SQLModel objects

    Returns:
        Dictionary with same keys but values as {id: object} dicts
    """
    return {key: {obj.id: obj for obj in items} for key, items in db_results.items()}


def get_token_name(symbol: str) -> str:
    """Get token full name from symbol.

    Args:
        symbol: Token symbol (e.g., 'USDT', 'ETH')

    Returns:
        Full token name
    """
    names = {
        "USDT": "Tether",
        "USDC": "USD Coin",
        "ETH": "Ethereum",
        "BTC": "Bitcoin",
        "TRX": "TRON",
        "SOL": "Solana",
    }
    return names.get(symbol, symbol)
