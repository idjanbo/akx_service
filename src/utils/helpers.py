"""Response model builder utilities."""

from typing import Any


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
