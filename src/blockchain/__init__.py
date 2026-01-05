"""Blockchain service module.

Provides abstraction layer for interacting with different blockchains.
"""

from src.blockchain.base import (
    BlockchainService,
    TransactionInfo,
    TransactionResult,
    TransactionStatus,
    WalletInfo,
)
from src.blockchain.factory import (
    get_blockchain_service,
    get_supported_chains,
)

__all__ = [
    "BlockchainService",
    "TransactionInfo",
    "TransactionResult",
    "TransactionStatus",
    "WalletInfo",
    "get_blockchain_service",
    "get_supported_chains",
]
