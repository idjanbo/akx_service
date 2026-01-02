"""Chains module - blockchain abstraction layer."""

from src.chains.base import BalanceInfo, ChainInterface, TransactionResult, WalletInfo
from src.chains.tron import TronChain, get_tron_chain
from src.models.wallet import Chain


def get_chain(chain: Chain | str) -> ChainInterface:
    """Factory function to get chain implementation.

    Args:
        chain: Chain enum or string name

    Returns:
        ChainInterface implementation for the specified chain

    Raises:
        ValueError: If chain is not supported
    """
    if isinstance(chain, str):
        chain = Chain(chain.lower())

    match chain:
        case Chain.TRON:
            return get_tron_chain()
        case Chain.ETHEREUM:
            raise NotImplementedError("Ethereum chain not yet implemented")
        case Chain.SOLANA:
            raise NotImplementedError("Solana chain not yet implemented")
        case _:
            raise ValueError(f"Unsupported chain: {chain}")


__all__ = [
    # Base
    "ChainInterface",
    "WalletInfo",
    "TransactionResult",
    "BalanceInfo",
    # Implementations
    "TronChain",
    "get_tron_chain",
    # Factory
    "get_chain",
]
