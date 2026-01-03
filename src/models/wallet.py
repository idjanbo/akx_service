"""AKX Crypto Payment Gateway - Wallet model.

Note: The Chain and Token enums below are deprecated.
Use the Chain and Token tables (models/chain.py and models/token.py) instead.
These are kept for backward compatibility during migration.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.chain import Chain
    from src.models.token import Token
    from src.models.user import User


# DEPRECATED: Use Chain table instead
class ChainEnum(str, Enum):
    """Supported blockchain networks (DEPRECATED).

    This enum is deprecated. Use the Chain table instead.
    """

    TRON = "tron"
    ETHEREUM = "ethereum"
    SOLANA = "solana"


# DEPRECATED: Use Token table instead
class TokenEnum(str, Enum):
    """Supported tokens/currencies (DEPRECATED).

    This enum is deprecated. Use the Token table instead.
    """

    USDT = "usdt"  # Tether USD
    USDC = "usdc"  # USD Coin
    ETH = "eth"  # Native Ethereum
    TRX = "trx"  # Native TRON
    SOL = "sol"  # Native Solana


# DEPRECATED: Token contract addresses - use TokenChainSupport table instead
TOKEN_CONTRACTS_DEPRECATED: dict[ChainEnum, dict[TokenEnum, str]] = {
    ChainEnum.TRON: {
        TokenEnum.USDT: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        TokenEnum.USDC: "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8",
        TokenEnum.TRX: "",
    },
    ChainEnum.ETHEREUM: {
        TokenEnum.USDT: "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        TokenEnum.USDC: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        TokenEnum.ETH: "",
    },
    ChainEnum.SOLANA: {
        TokenEnum.USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        TokenEnum.USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        TokenEnum.SOL: "",
    },
}


# DEPRECATED: Token decimals - use Token.decimals instead
TOKEN_DECIMALS_DEPRECATED: dict[TokenEnum, int] = {
    TokenEnum.USDT: 6,
    TokenEnum.USDC: 6,
    TokenEnum.ETH: 18,
    TokenEnum.TRX: 6,
    TokenEnum.SOL: 9,
}


# DEPRECATED: Payment method expiry - can be moved to TokenChainSupport table
PAYMENT_METHOD_EXPIRY_MINUTES_DEPRECATED: dict[ChainEnum, dict[TokenEnum, int]] = {
    ChainEnum.TRON: {
        TokenEnum.USDT: 30,
        TokenEnum.USDC: 30,
        TokenEnum.TRX: 15,
    },
    ChainEnum.ETHEREUM: {
        TokenEnum.USDT: 60,
        TokenEnum.USDC: 60,
        TokenEnum.ETH: 60,
    },
    ChainEnum.SOLANA: {
        TokenEnum.USDT: 15,
        TokenEnum.USDC: 15,
        TokenEnum.SOL: 10,
    },
}

DEFAULT_EXPIRY_MINUTES = 30


# DEPRECATED: Use database queries instead
def get_payment_method_expiry_deprecated(chain: ChainEnum, token: TokenEnum) -> int:
    """DEPRECATED: Use TokenChainSupport table instead."""
    return PAYMENT_METHOD_EXPIRY_MINUTES_DEPRECATED.get(chain, {}).get(
        token, DEFAULT_EXPIRY_MINUTES
    )


def get_token_contract_deprecated(chain: ChainEnum, token: TokenEnum) -> str:
    """DEPRECATED: Use TokenChainSupport table instead."""
    return TOKEN_CONTRACTS_DEPRECATED.get(chain, {}).get(token, "")


def get_token_decimals_deprecated(token: TokenEnum) -> int:
    """DEPRECATED: Use Token table instead."""
    return TOKEN_DECIMALS_DEPRECATED.get(token, 6)


class WalletType(str, Enum):
    """Wallet purpose types."""

    DEPOSIT = "deposit"  # Merchant deposit address
    GAS = "gas"  # System gas fee wallet
    COLD = "cold"  # Cold storage for collected funds


class Wallet(SQLModel, table=True):
    """Wallet model - blockchain addresses with encrypted private keys.

    Security Note:
        The `encrypted_private_key` field stores AES-256-GCM encrypted keys.
        NEVER store plaintext private keys.

    Note:
        This model now uses foreign keys to Chain and Token tables instead
        of enums. The chain_id and token_id fields reference the respective
        tables for better flexibility and management.

    Attributes:
        id: Auto-increment primary key
        user_id: Owner merchant (nullable for system wallets)
        chain_id: Reference to Chain table
        token_id: Reference to Token table (for token-specific wallets)
        address: Public blockchain address (indexed)
        encrypted_private_key: AES-encrypted private key
        wallet_type: Purpose (deposit, gas, cold)
        is_active: Whether wallet is in use
        label: Optional human-readable name
        balance: Cached balance (updated by scanner)
    """

    __tablename__ = "wallets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)

    # New: Use foreign keys instead of enums
    chain_id: int = Field(foreign_key="chains.id", index=True)
    token_id: int | None = Field(default=None, foreign_key="tokens.id", index=True)

    address: str = Field(max_length=255, index=True, unique=True)
    encrypted_private_key: str = Field(max_length=1024)
    wallet_type: WalletType = Field(default=WalletType.DEPOSIT)
    is_active: bool = Field(default=True)
    label: str | None = Field(default=None, max_length=255)

    # Cached balance (string to preserve precision)
    balance: str = Field(default="0", max_length=50)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional["User"] = Relationship(back_populates="wallets")
    chain: Optional["Chain"] = Relationship()
    token: Optional["Token"] = Relationship()
