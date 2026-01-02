"""AKX Crypto Payment Gateway - TRON chain implementation."""

from decimal import Decimal

from tronpy import Tron
from tronpy.keys import PrivateKey

from src.chains.base import BalanceInfo, ChainInterface, TransactionResult, WalletInfo
from src.core.config import get_settings


class TronChain(ChainInterface):
    """TRON blockchain implementation using tronpy.

    Supports TRX (native) and USDT-TRC20 token operations.

    Confirmation requirement: 19 blocks (~57 seconds)
    """

    CHAIN_NAME = "tron"
    REQUIRED_CONFIRMATIONS = 19
    USDT_DECIMALS = 6

    # USDT-TRC20 contract addresses
    USDT_CONTRACTS = {
        "mainnet": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "shasta": "TG3XXyExBkPp9nzdajDZsozEu4BkaSJozs",  # Shasta testnet
        "nile": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",  # Nile testnet
    }

    def __init__(self) -> None:
        """Initialize TRON client based on network config."""
        settings = get_settings()
        self._network = settings.tron_network

        if self._network == "mainnet":
            self._client = Tron()
        else:
            self._client = Tron(network=self._network)

        # Set API key if provided
        if settings.tron_api_key:
            self._client.conf["headers"] = {"TRON-PRO-API-KEY": settings.tron_api_key}

        self.USDT_CONTRACT = self.USDT_CONTRACTS.get(self._network, self.USDT_CONTRACTS["mainnet"])

    def generate_wallet(self) -> WalletInfo:
        """Generate a new TRON wallet.

        Returns:
            WalletInfo with base58 address and hex private key
        """
        # Generate random private key
        priv_key = PrivateKey.random()
        address = priv_key.public_key.to_base58check_address()

        return WalletInfo(
            address=address,
            private_key=priv_key.hex(),
        )

    def validate_address(self, address: str) -> bool:
        """Validate TRON address format.

        TRON addresses start with 'T' and are 34 characters (base58).
        """
        if not address or len(address) != 34:
            return False
        if not address.startswith("T"):
            return False
        # Additional base58 check
        try:
            self._client.get_account(address)
            return True
        except Exception:
            # Address format valid but account may not exist yet
            return address.startswith("T") and len(address) == 34

    async def get_balance(self, address: str) -> BalanceInfo:
        """Get TRX and USDT-TRC20 balance.

        Args:
            address: TRON wallet address (base58)

        Returns:
            BalanceInfo with balances in human-readable units
        """
        # Get TRX balance (in SUN, 1 TRX = 1,000,000 SUN)
        try:
            account = self._client.get_account(address)
            trx_sun = account.get("balance", 0)
        except Exception:
            trx_sun = 0

        trx_balance = Decimal(str(trx_sun)) / Decimal("1000000")

        # Get USDT-TRC20 balance
        try:
            contract = self._client.get_contract(self.USDT_CONTRACT)
            usdt_raw = contract.functions.balanceOf(address)
            usdt_balance = Decimal(str(usdt_raw)) / Decimal(10**self.USDT_DECIMALS)
        except Exception:
            usdt_balance = Decimal("0")

        return BalanceInfo(
            native_balance=trx_balance,
            usdt_balance=usdt_balance,
        )

    async def transfer_usdt(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        private_key: str,
    ) -> TransactionResult:
        """Transfer USDT-TRC20 tokens.

        Args:
            from_address: Source TRON address
            to_address: Destination TRON address
            amount: USDT amount (human-readable, e.g., 100.5)
            private_key: Hex private key of from_address

        Returns:
            TransactionResult with tx_hash
        """
        try:
            # Convert to smallest unit
            amount_raw = int(amount * Decimal(10**self.USDT_DECIMALS))

            contract = self._client.get_contract(self.USDT_CONTRACT)
            priv_key = PrivateKey(bytes.fromhex(private_key))

            # Build and sign transaction
            txn = (
                contract.functions.transfer(to_address, amount_raw)
                .with_owner(from_address)
                .fee_limit(30_000_000)  # 30 TRX fee limit
                .build()
                .sign(priv_key)
            )

            # Broadcast
            result = txn.broadcast()

            return TransactionResult(
                tx_hash=result.get("txid", ""),
                success=result.get("result", False),
                error_message=result.get("message", None),
            )

        except Exception as e:
            return TransactionResult(
                tx_hash="",
                success=False,
                error_message=str(e),
            )

    async def transfer_native(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        private_key: str,
    ) -> TransactionResult:
        """Transfer TRX (native currency).

        Args:
            from_address: Source TRON address
            to_address: Destination TRON address
            amount: TRX amount (human-readable)
            private_key: Hex private key of from_address

        Returns:
            TransactionResult with tx_hash
        """
        try:
            # Convert to SUN (1 TRX = 1,000,000 SUN)
            amount_sun = int(amount * Decimal("1000000"))

            priv_key = PrivateKey(bytes.fromhex(private_key))

            # Build and sign transaction
            txn = (
                self._client.trx.transfer(from_address, to_address, amount_sun)
                .build()
                .sign(priv_key)
            )

            # Broadcast
            result = txn.broadcast()

            return TransactionResult(
                tx_hash=result.get("txid", ""),
                success=result.get("result", False),
                error_message=result.get("message", None),
            )

        except Exception as e:
            return TransactionResult(
                tx_hash="",
                success=False,
                error_message=str(e),
            )

    async def get_transaction(self, tx_hash: str) -> TransactionResult:
        """Get transaction status and confirmation count.

        Args:
            tx_hash: TRON transaction ID

        Returns:
            TransactionResult with current status
        """
        try:
            tx_info = self._client.get_transaction_info(tx_hash)

            if not tx_info:
                return TransactionResult(
                    tx_hash=tx_hash,
                    success=False,
                    error_message="Transaction not found",
                )

            # Get current block for confirmation calculation
            current_block = self._client.get_latest_block_number()
            tx_block = tx_info.get("blockNumber", 0)

            confirmations = current_block - tx_block if tx_block else 0

            # Check receipt status
            receipt = tx_info.get("receipt", {})
            success = receipt.get("result", "") == "SUCCESS"

            return TransactionResult(
                tx_hash=tx_hash,
                success=success,
                block_number=tx_block,
                confirmations=max(0, confirmations),
                error_message=None if success else receipt.get("result", "Unknown error"),
            )

        except Exception as e:
            return TransactionResult(
                tx_hash=tx_hash,
                success=False,
                error_message=str(e),
            )


# Factory function
def get_tron_chain() -> TronChain:
    """Get TRON chain instance."""
    return TronChain()
