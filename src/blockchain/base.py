"""Base blockchain service interface.

Defines the abstract interface that all blockchain implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class TransactionStatus(str, Enum):
    """Transaction status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass
class TransactionResult:
    """Result of a blockchain transaction."""

    success: bool
    tx_hash: str | None = None
    error: str | None = None
    confirmations: int = 0
    status: TransactionStatus = TransactionStatus.PENDING


@dataclass
class TransactionInfo:
    """Information about a blockchain transaction."""

    tx_hash: str
    from_address: str
    to_address: str
    amount: Decimal
    token: str  # Token symbol or 'native'
    confirmations: int
    status: TransactionStatus
    block_number: int | None = None
    timestamp: int | None = None


@dataclass
class WalletInfo:
    """Wallet information from blockchain."""

    address: str
    private_key: str


class BlockchainService(ABC):
    """Abstract base class for blockchain services.

    Each blockchain implementation (TRON, Ethereum, Solana) must implement
    this interface to provide consistent functionality across chains.
    """

    @property
    @abstractmethod
    def chain_code(self) -> str:
        """Return the chain code (e.g., 'TRON', 'ETHEREUM', 'SOLANA')."""
        pass

    @property
    @abstractmethod
    def required_confirmations(self) -> int:
        """Return the number of confirmations required for finality."""
        pass

    # ============ Wallet Operations ============

    @abstractmethod
    async def generate_wallet(self) -> WalletInfo:
        """Generate a new wallet address and private key.

        Returns:
            WalletInfo with address and private_key
        """
        pass

    @abstractmethod
    def validate_address(self, address: str) -> bool:
        """Validate if an address is valid for this chain.

        Args:
            address: The address to validate

        Returns:
            True if valid, False otherwise
        """
        pass

    # ============ Balance Operations ============

    @abstractmethod
    async def get_native_balance(self, address: str) -> Decimal:
        """Get native token balance (e.g., TRX, ETH, SOL).

        Args:
            address: Wallet address

        Returns:
            Balance as Decimal
        """
        pass

    @abstractmethod
    async def get_token_balance(
        self,
        address: str,
        contract_address: str,
        decimals: int = 6,
    ) -> Decimal:
        """Get token balance for a specific contract.

        Args:
            address: Wallet address
            contract_address: Token contract address
            decimals: Token decimals

        Returns:
            Balance as Decimal
        """
        pass

    # ============ Transaction Operations ============

    @abstractmethod
    async def send_native(
        self,
        from_private_key: str,
        to_address: str,
        amount: Decimal,
    ) -> TransactionResult:
        """Send native token (TRX, ETH, SOL).

        Args:
            from_private_key: Sender's private key
            to_address: Recipient address
            amount: Amount to send

        Returns:
            TransactionResult with tx_hash or error
        """
        pass

    @abstractmethod
    async def send_token(
        self,
        from_private_key: str,
        to_address: str,
        contract_address: str,
        amount: Decimal,
        decimals: int = 6,
    ) -> TransactionResult:
        """Send token (USDT, USDC, etc.).

        Args:
            from_private_key: Sender's private key
            to_address: Recipient address
            contract_address: Token contract address
            amount: Amount to send
            decimals: Token decimals

        Returns:
            TransactionResult with tx_hash or error
        """
        pass

    # ============ Transaction Query ============

    @abstractmethod
    async def get_transaction(self, tx_hash: str) -> TransactionInfo | None:
        """Get transaction details by hash.

        Args:
            tx_hash: Transaction hash

        Returns:
            TransactionInfo or None if not found
        """
        pass

    @abstractmethod
    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get number of confirmations for a transaction.

        Args:
            tx_hash: Transaction hash

        Returns:
            Number of confirmations
        """
        pass

    # ============ Utility Methods ============

    def to_smallest_unit(self, amount: Decimal, decimals: int) -> int:
        """Convert amount to smallest unit (e.g., wei, sun).

        Args:
            amount: Amount in standard unit
            decimals: Token decimals

        Returns:
            Amount in smallest unit as integer
        """
        return int(amount * (10**decimals))

    def from_smallest_unit(self, amount: int, decimals: int) -> Decimal:
        """Convert from smallest unit to standard unit.

        Args:
            amount: Amount in smallest unit
            decimals: Token decimals

        Returns:
            Amount in standard unit as Decimal
        """
        return Decimal(amount) / Decimal(10**decimals)
