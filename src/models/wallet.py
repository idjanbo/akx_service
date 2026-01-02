"""AKX Crypto Payment Gateway - Wallet model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.user import User


class Chain(str, Enum):
    """Supported blockchain networks."""

    TRON = "tron"
    ETHEREUM = "ethereum"
    SOLANA = "solana"


class Token(str, Enum):
    """Supported tokens/currencies.

    Each token can exist on multiple chains.
    Chain + Token uniquely identifies a payment method.
    """

    USDT = "usdt"  # Tether USD
    USDC = "usdc"  # USD Coin
    ETH = "eth"  # Native Ethereum (only on Ethereum chain)
    TRX = "trx"  # Native TRON (only on TRON chain)
    SOL = "sol"  # Native Solana (only on Solana chain)


# Token contract addresses per chain
TOKEN_CONTRACTS: dict[Chain, dict[Token, str]] = {
    Chain.TRON: {
        Token.USDT: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",  # USDT-TRC20 mainnet
        Token.USDC: "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8",  # USDC-TRC20 mainnet
        Token.TRX: "",  # Native token, no contract
    },
    Chain.ETHEREUM: {
        Token.USDT: "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT-ERC20
        Token.USDC: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC-ERC20
        Token.ETH: "",  # Native token
    },
    Chain.SOLANA: {
        Token.USDT: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT SPL
        Token.USDC: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC SPL
        Token.SOL: "",  # Native token
    },
}


# Token decimals
TOKEN_DECIMALS: dict[Token, int] = {
    Token.USDT: 6,
    Token.USDC: 6,
    Token.ETH: 18,
    Token.TRX: 6,
    Token.SOL: 9,
}


# Payment method expiry time (minutes) - Chain + Token
# Different payment methods can have different expiry times
PAYMENT_METHOD_EXPIRY_MINUTES: dict[Chain, dict[Token, int]] = {
    Chain.TRON: {
        Token.USDT: 30,  # TRON USDT: 30 minutes
        Token.USDC: 30,
        Token.TRX: 15,  # Native TRX: faster confirmation
    },
    Chain.ETHEREUM: {
        Token.USDT: 60,  # ETH is slower, give more time
        Token.USDC: 60,
        Token.ETH: 60,
    },
    Chain.SOLANA: {
        Token.USDT: 15,  # Solana is fast
        Token.USDC: 15,
        Token.SOL: 10,
    },
}

# Default expiry if not specified
DEFAULT_EXPIRY_MINUTES = 30


def get_payment_method_expiry(chain: Chain, token: Token) -> int:
    """Get expiry time in minutes for a payment method.

    Payment method is uniquely identified by: chain + token

    Args:
        chain: Blockchain network
        token: Token/currency

    Returns:
        Expiry time in minutes
    """
    return PAYMENT_METHOD_EXPIRY_MINUTES.get(chain, {}).get(token, DEFAULT_EXPIRY_MINUTES)


def get_token_contract(chain: Chain, token: Token) -> str:
    """Get token contract address for a chain.

    Returns empty string for native tokens.
    """
    return TOKEN_CONTRACTS.get(chain, {}).get(token, "")


def get_token_decimals(token: Token) -> int:
    """Get decimal places for a token."""
    return TOKEN_DECIMALS.get(token, 6)


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

    Attributes:
        id: Auto-increment primary key
        user_id: Owner merchant (nullable for system wallets)
        chain: Blockchain network (TRON, ETH, SOL)
        address: Public blockchain address (indexed)
        encrypted_private_key: AES-encrypted private key
        wallet_type: Purpose (deposit, gas, cold)
        is_active: Whether wallet is in use
        label: Optional human-readable name
    """

    __tablename__ = "wallets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    chain: Chain = Field(index=True)
    address: str = Field(max_length=255, index=True)
    encrypted_private_key: str = Field(max_length=1024)
    wallet_type: WalletType = Field(default=WalletType.DEPOSIT)
    is_active: bool = Field(default=True)
    label: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional["User"] = Relationship(back_populates="wallets")
