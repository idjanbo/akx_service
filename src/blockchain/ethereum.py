"""Ethereum blockchain service implementation.

Provides Ethereum-specific blockchain operations using web3.py library.
"""

import logging
from decimal import Decimal

from eth_account import Account
from web3 import AsyncWeb3

from src.blockchain.base import (
    BlockchainService,
    TransactionInfo,
    TransactionResult,
    TransactionStatus,
    WalletInfo,
)
from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Standard ERC-20 ABI for transfer and balanceOf
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


class EthereumService(BlockchainService):
    """Ethereum blockchain service implementation.

    Supports ERC-20 tokens (USDT, USDC) and native ETH transfers.
    Uses web3.py library for blockchain interactions.
    """

    def __init__(self):
        """Initialize Ethereum service with RPC configuration."""
        settings = get_settings()
        self._rpc_url = settings.eth_rpc_url

        if not self._rpc_url:
            raise ValueError("ETH_RPC_URL is required for Ethereum service")

        # Use AsyncWeb3 with the RPC URL directly
        self._w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpc_url))

    @property
    def chain_code(self) -> str:
        return "ETHEREUM"

    @property
    def required_confirmations(self) -> int:
        return 12  # Ethereum requires ~12 confirmations for finality

    # ============ Wallet Operations ============

    async def generate_wallet(self) -> WalletInfo:
        """Generate a new Ethereum wallet."""
        account = Account.create()
        return WalletInfo(
            address=account.address,
            private_key=account.key.hex(),
        )

    def validate_address(self, address: str) -> bool:
        """Validate Ethereum address format."""
        if not address:
            return False
        return self._w3.is_address(address)

    # ============ Balance Operations ============

    async def get_native_balance(self, address: str) -> Decimal:
        """Get ETH balance."""
        try:
            balance_wei = await self._w3.eth.get_balance(address)
            return self.from_smallest_unit(balance_wei, 18)
        except Exception as e:
            logger.error(f"Failed to get ETH balance for {address}: {e}")
            return Decimal("0")

    async def get_token_balance(
        self,
        address: str,
        contract_address: str,
        decimals: int = 6,
    ) -> Decimal:
        """Get ERC-20 token balance."""
        try:
            contract = self._w3.eth.contract(
                address=self._w3.to_checksum_address(contract_address),
                abi=ERC20_ABI,
            )
            balance = await contract.functions.balanceOf(
                self._w3.to_checksum_address(address)
            ).call()
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
        """Send ETH."""
        try:
            # Get account from private key
            if not from_private_key.startswith("0x"):
                from_private_key = "0x" + from_private_key
            account = Account.from_key(from_private_key)
            from_address = account.address

            # Get nonce
            nonce = await self._w3.eth.get_transaction_count(from_address)

            # Get gas price
            gas_price = await self._w3.eth.gas_price

            # Build transaction
            tx = {
                "nonce": nonce,
                "to": self._w3.to_checksum_address(to_address),
                "value": self.to_smallest_unit(amount, 18),
                "gas": 21000,  # Standard ETH transfer gas
                "gasPrice": gas_price,
                "chainId": await self._w3.eth.chain_id,
            }

            # Sign and send
            signed_tx = self._w3.eth.account.sign_transaction(tx, from_private_key)
            tx_hash = await self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(f"ETH transfer successful: {tx_hash.hex()}")
            return TransactionResult(
                success=True,
                tx_hash=tx_hash.hex(),
                status=TransactionStatus.PENDING,
            )

        except Exception as e:
            logger.exception(f"ETH transfer error: {e}")
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
        """Send ERC-20 token."""
        try:
            # Get account from private key
            if not from_private_key.startswith("0x"):
                from_private_key = "0x" + from_private_key
            account = Account.from_key(from_private_key)
            from_address = account.address

            # Get contract
            contract = self._w3.eth.contract(
                address=self._w3.to_checksum_address(contract_address),
                abi=ERC20_ABI,
            )

            # Amount in smallest unit
            amount_smallest = self.to_smallest_unit(amount, decimals)

            # Get nonce
            nonce = await self._w3.eth.get_transaction_count(from_address)

            # Get gas price
            gas_price = await self._w3.eth.gas_price

            # Build transfer transaction
            tx = await contract.functions.transfer(
                self._w3.to_checksum_address(to_address),
                amount_smallest,
            ).build_transaction(
                {
                    "from": from_address,
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "chainId": await self._w3.eth.chain_id,
                }
            )

            # Estimate gas
            tx["gas"] = await self._w3.eth.estimate_gas(tx)

            # Sign and send
            signed_tx = self._w3.eth.account.sign_transaction(tx, from_private_key)
            tx_hash = await self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(f"ERC-20 transfer successful: {tx_hash.hex()}")
            return TransactionResult(
                success=True,
                tx_hash=tx_hash.hex(),
                status=TransactionStatus.PENDING,
            )

        except Exception as e:
            logger.exception(f"ERC-20 transfer error: {e}")
            return TransactionResult(
                success=False,
                error=str(e),
                status=TransactionStatus.FAILED,
            )

    # ============ Transaction Query ============

    async def get_transaction(self, tx_hash: str) -> TransactionInfo | None:
        """Get transaction details."""
        try:
            tx = await self._w3.eth.get_transaction(tx_hash)
            if not tx:
                return None

            receipt = await self._w3.eth.get_transaction_receipt(tx_hash)

            # Determine status
            if receipt:
                if receipt["status"] == 1:
                    status = TransactionStatus.CONFIRMED
                else:
                    status = TransactionStatus.FAILED
            else:
                status = TransactionStatus.PENDING

            # Parse transaction
            from_address = tx["from"]
            to_address = tx["to"] or ""
            amount = self.from_smallest_unit(tx["value"], 18)
            token = "ETH"

            # Check if it's a token transfer
            if tx["input"] and len(tx["input"]) > 10:
                input_data = tx["input"].hex() if isinstance(tx["input"], bytes) else tx["input"]
                # ERC-20 transfer method ID: 0xa9059cbb
                if input_data.startswith("0xa9059cbb"):
                    token = "TOKEN"
                    # Decode transfer data
                    try:
                        to_address = "0x" + input_data[34:74]
                        amount_hex = input_data[74:138]
                        amount = self.from_smallest_unit(int(amount_hex, 16), 6)
                    except Exception:
                        pass

            confirmations = await self.get_transaction_confirmations(tx_hash)

            return TransactionInfo(
                tx_hash=tx_hash,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                token=token,
                confirmations=confirmations,
                status=status,
                block_number=tx.get("blockNumber"),
                timestamp=None,  # Would need to fetch block for timestamp
            )

        except Exception as e:
            logger.error(f"Failed to get transaction {tx_hash}: {e}")
            return None

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get transaction confirmation count."""
        try:
            tx = await self._w3.eth.get_transaction(tx_hash)
            if not tx or not tx.get("blockNumber"):
                return 0

            latest_block = await self._w3.eth.block_number
            confirmations = latest_block - tx["blockNumber"]
            return max(0, confirmations)

        except Exception as e:
            logger.error(f"Failed to get confirmations for {tx_hash}: {e}")
            return 0

    async def close(self):
        """Close the provider connection."""
        try:
            if hasattr(self._w3.provider, "disconnect"):
                await self._w3.provider.disconnect()
        except Exception:
            pass
