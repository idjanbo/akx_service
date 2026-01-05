"""Blockchain service factory.

Provides factory method to get the appropriate blockchain service
based on chain code.
"""

import logging
from functools import lru_cache

from src.blockchain.base import BlockchainService

logger = logging.getLogger(__name__)

# Chain code mapping
CHAIN_CODES = {
    "TRON": "tron",
    "tron": "tron",
    "ETHEREUM": "ethereum",
    "ethereum": "ethereum",
    "ETH": "ethereum",
    "eth": "ethereum",
    "SOLANA": "solana",
    "solana": "solana",
    "SOL": "solana",
    "sol": "solana",
}


@lru_cache(maxsize=3)
def get_blockchain_service(chain_code: str) -> BlockchainService:
    """Get blockchain service for the specified chain.

    Uses caching to reuse service instances.

    Args:
        chain_code: Chain code (e.g., 'TRON', 'tron', 'ETHEREUM', 'eth', 'SOLANA', 'sol')

    Returns:
        BlockchainService instance

    Raises:
        ValueError: If chain code is not supported
    """
    normalized_code = CHAIN_CODES.get(chain_code)
    if not normalized_code:
        raise ValueError(f"Unsupported chain: {chain_code}")

    if normalized_code == "tron":
        from src.blockchain.tron import TronService

        return TronService()
    elif normalized_code == "ethereum":
        from src.blockchain.ethereum import EthereumService

        return EthereumService()
    elif normalized_code == "solana":
        from src.blockchain.solana import SolanaService

        return SolanaService()
    else:
        raise ValueError(f"Unsupported chain: {chain_code}")


def get_supported_chains() -> list[str]:
    """Get list of supported chain codes.

    Returns:
        List of chain codes
    """
    return ["TRON", "ETHEREUM", "SOLANA"]


async def close_all_services():
    """Close all cached blockchain service connections."""
    try:
        get_blockchain_service.cache_clear()
        logger.info("Blockchain services cache cleared")
    except Exception as e:
        logger.error(f"Error closing blockchain services: {e}")
