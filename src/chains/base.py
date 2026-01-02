"""AKX Crypto Payment Gateway - Chain interface abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class WalletInfo:
    """Generated wallet information."""

    address: str
    private_key: str  # Raw private key - encrypt before storage!


@dataclass
class TransactionResult:
    """Result of a blockchain transaction."""

    tx_hash: str
    success: bool
    block_number: int | None = None
    confirmations: int = 0
    error_message: str | None = None


@dataclass
class BalanceInfo:
    """Wallet balance information."""

    native_balance: Decimal  # TRX, ETH, SOL
    usdt_balance: Decimal  # USDT token balance


class ChainInterface(ABC):
    """Abstract interface for blockchain operations.

    All chain implementations (TRON, Ethereum, Solana) must implement this interface.

    Usage:
        chain = get_chain("tron")
        wallet = chain.generate_wallet()
        balance = await chain.get_balance(wallet.address)
    """

    # Chain-specific constants (override in subclasses)
    CHAIN_NAME: str = ""
    REQUIRED_CONFIRMATIONS: int = 1
    USDT_CONTRACT: str = ""
    USDT_DECIMALS: int = 6

    @abstractmethod
    def generate_wallet(self) -> WalletInfo:
        """Generate a new wallet (address + private key).

        Returns:
            WalletInfo with address and raw private key

        Security Note:
            Caller must encrypt private_key before database storage!
        """
        pass

    @abstractmethod
    def validate_address(self, address: str) -> bool:
        """Validate if an address is valid for this chain.

        Args:
            address: Blockchain address to validate

        Returns:
            True if valid address format
        """
        pass

    @abstractmethod
    async def get_balance(self, address: str) -> BalanceInfo:
        """Get native and USDT balance for an address.

        Args:
            address: Wallet address

        Returns:
            BalanceInfo with native and USDT balances
        """
        pass

    @abstractmethod
    async def transfer_usdt(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        private_key: str,
    ) -> TransactionResult:
        """Transfer USDT tokens.

        Args:
            from_address: Source wallet address
            to_address: Destination address
            amount: USDT amount to transfer
            private_key: Decrypted private key of from_address

        Returns:
            TransactionResult with tx_hash and status
        """
        pass

    @abstractmethod
    async def transfer_native(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        private_key: str,
    ) -> TransactionResult:
        """Transfer native currency (TRX/ETH/SOL) for gas.

        Args:
            from_address: Source wallet address
            to_address: Destination address
            amount: Native currency amount
            private_key: Decrypted private key of from_address

        Returns:
            TransactionResult with tx_hash and status
        """
        pass

    @abstractmethod
    async def get_transaction(self, tx_hash: str) -> TransactionResult:
        """Get transaction status and confirmations.

        Args:
            tx_hash: Transaction hash to query

        Returns:
            TransactionResult with current confirmation count
        """
        pass

    def is_confirmed(self, confirmations: int) -> bool:
        """Check if transaction has enough confirmations.

        Args:
            confirmations: Current confirmation count

        Returns:
            True if >= REQUIRED_CONFIRMATIONS
        """
        return confirmations >= self.REQUIRED_CONFIRMATIONS
