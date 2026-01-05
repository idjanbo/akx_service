"""TRON blockchain service implementation.

Provides TRON-specific blockchain operations using tronpy library.
"""

import logging
from decimal import Decimal

from tronpy import AsyncTron
from tronpy.keys import PrivateKey
from tronpy.providers.async_http import AsyncHTTPProvider

from src.blockchain.base import (
    BlockchainService,
    TransactionInfo,
    TransactionResult,
    TransactionStatus,
    WalletInfo,
)
from src.core.config import get_settings

logger = logging.getLogger(__name__)


class TronService(BlockchainService):
    """TRON blockchain service implementation.

    Supports TRC-20 tokens (USDT, USDC) and native TRX transfers.
    Uses tronpy library for blockchain interactions.
    """

    # TRC-20 transfer function selector
    TRC20_TRANSFER_SELECTOR = "a9059cbb"

    def __init__(self):
        """Initialize TRON service with network configuration."""
        settings = get_settings()
        self._network = settings.tron_network
        self._api_key = settings.tron_api_key

        # Initialize client based on network
        if self._network == "mainnet":
            provider = AsyncHTTPProvider(
                "https://api.trongrid.io",
                api_key=self._api_key if self._api_key else None,
            )
            self._client = AsyncTron(provider=provider)
        elif self._network == "shasta":
            self._client = AsyncTron(network="shasta")
        else:  # nile
            self._client = AsyncTron(network="nile")

    @property
    def chain_code(self) -> str:
        return "TRON"

    @property
    def required_confirmations(self) -> int:
        return 19  # TRON requires 19 confirmations for finality

    # ============ Wallet Operations ============

    async def generate_wallet(self) -> WalletInfo:
        """Generate a new TRON wallet."""
        priv_key = PrivateKey.random()
        address = priv_key.public_key.to_base58check_address()
        return WalletInfo(
            address=address,
            private_key=priv_key.hex(),
        )

    def validate_address(self, address: str) -> bool:
        """Validate TRON address format."""
        if not address:
            return False
        # TRON addresses start with 'T' and are 34 characters
        if not address.startswith("T"):
            return False
        if len(address) != 34:
            return False
        # Basic base58 check
        try:
            import base58

            base58.b58decode_check(address)
            return True
        except Exception:
            return False

    # ============ Balance Operations ============

    async def get_native_balance(self, address: str) -> Decimal:
        """Get TRX balance."""
        try:
            balance_sun = await self._client.get_account_balance(address)
            return Decimal(str(balance_sun))
        except Exception as e:
            logger.error(f"Failed to get TRX balance for {address}: {e}")
            return Decimal("0")

    async def get_token_balance(
        self,
        address: str,
        contract_address: str,
        decimals: int = 6,
    ) -> Decimal:
        """Get TRC-20 token balance."""
        try:
            contract = await self._client.get_contract(contract_address)
            balance = await contract.functions.balanceOf(address)
            return self.from_smallest_unit(balance, decimals)
        except Exception as e:
            logger.error(
                f"Failed to get token balance for {address} (contract: {contract_address}): {e}"
            )
            return Decimal("0")

    # ============ Transaction Operations ============

    async def send_native(
        self,
        from_private_key: str,
        to_address: str,
        amount: Decimal,
    ) -> TransactionResult:
        """Send TRX."""
        try:
            priv_key = PrivateKey(bytes.fromhex(from_private_key))
            from_address = priv_key.public_key.to_base58check_address()

            # Amount in SUN (1 TRX = 1,000,000 SUN)
            amount_sun = self.to_smallest_unit(amount, 6)

            # Build and sign transaction
            txn = (
                self._client.trx.transfer(from_address, to_address, amount_sun)
                .build()
                .sign(priv_key)
            )

            # Broadcast
            result = await txn.broadcast()

            if result.get("result"):
                tx_hash = result.get("txid")
                logger.info(f"TRX transfer successful: {tx_hash}")
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash,
                    status=TransactionStatus.PENDING,
                )
            else:
                error_msg = result.get("message", "Unknown error")
                logger.error(f"TRX transfer failed: {error_msg}")
                return TransactionResult(
                    success=False,
                    error=error_msg,
                    status=TransactionStatus.FAILED,
                )

        except Exception as e:
            logger.exception(f"TRX transfer error: {e}")
            return TransactionResult(
                success=False,
                error=str(e),
                status=TransactionStatus.FAILED,
            )

    async def send_token(
        self,
        from_private_key: str,
        to_address: str,
        contract_address: str,
        amount: Decimal,
        decimals: int = 6,
    ) -> TransactionResult:
        """Send TRC-20 token."""
        try:
            priv_key = PrivateKey(bytes.fromhex(from_private_key))
            from_address = priv_key.public_key.to_base58check_address()

            # Get contract
            contract = await self._client.get_contract(contract_address)

            # Amount in smallest unit
            amount_smallest = self.to_smallest_unit(amount, decimals)

            # Build transfer transaction
            txn = await contract.functions.transfer.with_owner(from_address)(
                to_address, amount_smallest
            )
            txn = txn.build().sign(priv_key)

            # Broadcast
            result = await txn.broadcast()

            if result.get("result"):
                tx_hash = result.get("txid")
                logger.info(f"TRC-20 transfer successful: {tx_hash}")
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash,
                    status=TransactionStatus.PENDING,
                )
            else:
                error_msg = result.get("message", "Unknown error")
                logger.error(f"TRC-20 transfer failed: {error_msg}")
                return TransactionResult(
                    success=False,
                    error=error_msg,
                    status=TransactionStatus.FAILED,
                )

        except Exception as e:
            logger.exception(f"TRC-20 transfer error: {e}")
            return TransactionResult(
                success=False,
                error=str(e),
                status=TransactionStatus.FAILED,
            )

    # ============ Transaction Query ============

    async def get_transaction(self, tx_hash: str) -> TransactionInfo | None:
        """Get transaction details."""
        try:
            tx_info = await self._client.get_transaction_info(tx_hash)
            if not tx_info:
                return None

            tx = await self._client.get_transaction(tx_hash)
            if not tx:
                return None

            # Parse transaction data
            contract_data = tx.get("raw_data", {}).get("contract", [{}])[0]
            contract_type = contract_data.get("type")

            from_address = ""
            to_address = ""
            amount = Decimal("0")
            token = "TRX"

            if contract_type == "TransferContract":
                # Native TRX transfer
                value = contract_data.get("parameter", {}).get("value", {})
                from_address = value.get("owner_address", "")
                to_address = value.get("to_address", "")
                amount = self.from_smallest_unit(value.get("amount", 0), 6)
            elif contract_type == "TriggerSmartContract":
                # Token transfer
                value = contract_data.get("parameter", {}).get("value", {})
                from_address = value.get("owner_address", "")
                # Parse TRC-20 transfer data
                data = value.get("data", "")
                if data.startswith(self.TRC20_TRANSFER_SELECTOR):
                    token = "TOKEN"  # Generic, actual symbol needs lookup

            # Determine status
            result = tx_info.get("receipt", {}).get("result")
            if result == "SUCCESS":
                status = TransactionStatus.CONFIRMED
            elif result:
                status = TransactionStatus.FAILED
            else:
                status = TransactionStatus.PENDING

            confirmations = await self.get_transaction_confirmations(tx_hash)

            return TransactionInfo(
                tx_hash=tx_hash,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                token=token,
                confirmations=confirmations,
                status=status,
                block_number=tx_info.get("blockNumber"),
                timestamp=tx_info.get("blockTimeStamp"),
            )

        except Exception as e:
            logger.error(f"Failed to get transaction {tx_hash}: {e}")
            return None

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get transaction confirmation count."""
        try:
            tx_info = await self._client.get_transaction_info(tx_hash)
            if not tx_info:
                return 0

            tx_block = tx_info.get("blockNumber")
            if not tx_block:
                return 0

            latest_block = await self.get_latest_block_number()
            confirmations = latest_block - tx_block
            return max(0, confirmations)

        except Exception as e:
            logger.error(f"Failed to get confirmations for {tx_hash}: {e}")
            return 0

    async def close(self):
        """Close the client connection."""
        try:
            await self._client.close()
        except Exception:
            pass
