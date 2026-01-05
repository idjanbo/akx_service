"""Solana blockchain service implementation.

Provides Solana-specific blockchain operations using solana-py library.
"""

import logging
from decimal import Decimal

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from src.blockchain.base import (
    BlockchainService,
    TransactionInfo,
    TransactionResult,
    TransactionStatus,
    WalletInfo,
)
from src.core.config import get_settings

logger = logging.getLogger(__name__)

# SPL Token Program ID
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


class SolanaService(BlockchainService):
    """Solana blockchain service implementation.

    Supports SPL tokens (USDT, USDC) and native SOL transfers.
    Uses solana-py library for blockchain interactions.
    """

    def __init__(self):
        """Initialize Solana service with RPC configuration."""
        settings = get_settings()
        self._rpc_url = settings.solana_rpc_url

        if not self._rpc_url:
            self._rpc_url = "https://api.mainnet-beta.solana.com"

        self._client = AsyncClient(self._rpc_url, commitment=Confirmed)

    @property
    def chain_code(self) -> str:
        return "SOLANA"

    @property
    def required_confirmations(self) -> int:
        return 32  # Solana requires 32 confirmations for finality

    # ============ Wallet Operations ============

    async def generate_wallet(self) -> WalletInfo:
        """Generate a new Solana wallet."""
        keypair = Keypair()
        return WalletInfo(
            address=str(keypair.pubkey()),
            private_key=keypair.secret().hex(),
        )

    def validate_address(self, address: str) -> bool:
        """Validate Solana address format."""
        if not address:
            return False
        try:
            # Solana addresses are base58 encoded, 32-44 characters
            if len(address) < 32 or len(address) > 44:
                return False
            Pubkey.from_string(address)
            return True
        except Exception:
            return False

    # ============ Balance Operations ============

    async def get_native_balance(self, address: str) -> Decimal:
        """Get SOL balance."""
        try:
            pubkey = Pubkey.from_string(address)
            response = await self._client.get_balance(pubkey)
            if response.value is not None:
                # SOL has 9 decimals (1 SOL = 1,000,000,000 lamports)
                return self.from_smallest_unit(response.value, 9)
            return Decimal("0")
        except Exception as e:
            logger.error(f"Failed to get SOL balance for {address}: {e}")
            return Decimal("0")

    async def get_token_balance(
        self,
        address: str,
        contract_address: str,
        decimals: int = 6,
    ) -> Decimal:
        """Get SPL token balance.

        Note: For SPL tokens, we need to find the associated token account.
        This is a simplified implementation.
        """
        try:
            owner = Pubkey.from_string(address)
            mint = Pubkey.from_string(contract_address)

            # Get token accounts for owner
            response = await self._client.get_token_accounts_by_owner(
                owner,
                {"mint": mint},
            )

            if response.value:
                # Sum up balances from all token accounts
                total_balance = 0
                for account in response.value:
                    account_data = account.account.data
                    # Parse account data to get balance
                    # Token account data layout: mint (32) + owner (32) + amount (8) + ...
                    if len(account_data) >= 72:
                        amount_bytes = bytes(account_data[64:72])
                        total_balance += int.from_bytes(amount_bytes, "little")

                return self.from_smallest_unit(total_balance, decimals)

            return Decimal("0")

        except Exception as e:
            logger.error(
                f"Failed to get token balance for {address} (mint: {contract_address}): {e}"
            )
            return Decimal("0")

    # ============ Transaction Operations ============

    async def send_native(
        self,
        from_private_key: str,
        to_address: str,
        amount: Decimal,
    ) -> TransactionResult:
        """Send SOL."""
        try:
            # Create keypair from private key
            secret_key = bytes.fromhex(from_private_key)
            keypair = Keypair.from_seed(secret_key[:32])
            from_pubkey = keypair.pubkey()
            to_pubkey = Pubkey.from_string(to_address)

            # Amount in lamports (1 SOL = 10^9 lamports)
            lamports = self.to_smallest_unit(amount, 9)

            # Get recent blockhash
            recent_blockhash = await self._client.get_latest_blockhash()

            # Create transfer instruction
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=from_pubkey,
                    to_pubkey=to_pubkey,
                    lamports=lamports,
                )
            )

            # Create and sign transaction
            tx = Transaction.new_signed_with_payer(
                instructions=[transfer_ix],
                payer=from_pubkey,
                signing_keypairs=[keypair],
                recent_blockhash=recent_blockhash.value.blockhash,
            )

            # Send transaction
            response = await self._client.send_transaction(tx)

            if response.value:
                tx_hash = str(response.value)
                logger.info(f"SOL transfer successful: {tx_hash}")
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash,
                    status=TransactionStatus.PENDING,
                )
            else:
                error_msg = "Transaction failed"
                logger.error(f"SOL transfer failed: {error_msg}")
                return TransactionResult(
                    success=False,
                    error=error_msg,
                    status=TransactionStatus.FAILED,
                )

        except Exception as e:
            logger.exception(f"SOL transfer error: {e}")
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
        """Send SPL token.

        Note: This is a simplified implementation. In production, you need to:
        1. Check if recipient has an associated token account
        2. Create the account if it doesn't exist
        3. Handle token account rent exemption
        """
        try:
            from spl.token.async_client import AsyncToken
            from spl.token.constants import TOKEN_PROGRAM_ID

            # Create keypair from private key
            secret_key = bytes.fromhex(from_private_key)
            keypair = Keypair.from_seed(secret_key[:32])
            from_pubkey = keypair.pubkey()

            mint = Pubkey.from_string(contract_address)
            to_pubkey = Pubkey.from_string(to_address)

            # Amount in smallest unit
            amount_smallest = self.to_smallest_unit(amount, decimals)

            # Get or create associated token accounts
            # This is simplified - in production, handle account creation
            token = AsyncToken(
                conn=self._client,
                pubkey=mint,
                program_id=TOKEN_PROGRAM_ID,
                payer=keypair,
            )

            # Get source token account
            source_account = await token.get_accounts_by_owner(from_pubkey)
            if not source_account.value:
                return TransactionResult(
                    success=False,
                    error="No source token account found",
                    status=TransactionStatus.FAILED,
                )

            source_token_account = source_account.value[0].pubkey

            # Get or create destination token account
            dest_account = await token.get_accounts_by_owner(to_pubkey)
            if dest_account.value:
                dest_token_account = dest_account.value[0].pubkey
            else:
                # Create associated token account for recipient
                # This requires additional implementation
                return TransactionResult(
                    success=False,
                    error="Recipient token account does not exist",
                    status=TransactionStatus.FAILED,
                )

            # Transfer tokens
            response = await token.transfer(
                source=source_token_account,
                dest=dest_token_account,
                owner=keypair,
                amount=amount_smallest,
            )

            if response.value:
                tx_hash = str(response.value)
                logger.info(f"SPL token transfer successful: {tx_hash}")
                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash,
                    status=TransactionStatus.PENDING,
                )
            else:
                return TransactionResult(
                    success=False,
                    error="Token transfer failed",
                    status=TransactionStatus.FAILED,
                )

        except Exception as e:
            logger.exception(f"SPL token transfer error: {e}")
            return TransactionResult(
                success=False,
                error=str(e),
                status=TransactionStatus.FAILED,
            )

    # ============ Transaction Query ============

    async def get_transaction(self, tx_hash: str) -> TransactionInfo | None:
        """Get transaction details."""
        try:
            from solders.signature import Signature

            signature = Signature.from_string(tx_hash)
            response = await self._client.get_transaction(
                signature,
                max_supported_transaction_version=0,
            )

            if not response.value:
                return None

            tx = response.value
            meta = tx.transaction.meta

            # Determine status
            if meta and meta.err is None:
                status = TransactionStatus.CONFIRMED
            elif meta and meta.err:
                status = TransactionStatus.FAILED
            else:
                status = TransactionStatus.PENDING

            # Parse transaction (simplified)
            # Full parsing requires understanding the transaction instructions
            from_address = ""
            to_address = ""
            amount = Decimal("0")
            token = "SOL"

            # Try to get account keys
            message = tx.transaction.transaction.message
            if hasattr(message, "account_keys"):
                keys = message.account_keys
                if len(keys) >= 2:
                    from_address = str(keys[0])
                    to_address = str(keys[1])

            # Get pre/post balances to calculate amount
            if meta and meta.pre_balances and meta.post_balances:
                if len(meta.pre_balances) >= 2:
                    amount_lamports = meta.pre_balances[0] - meta.post_balances[0]
                    if amount_lamports > 0:
                        amount = self.from_smallest_unit(amount_lamports, 9)

            confirmations = await self.get_transaction_confirmations(tx_hash)

            return TransactionInfo(
                tx_hash=tx_hash,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                token=token,
                confirmations=confirmations,
                status=status,
                block_number=tx.slot if hasattr(tx, "slot") else None,
                timestamp=tx.block_time if hasattr(tx, "block_time") else None,
            )

        except Exception as e:
            logger.error(f"Failed to get transaction {tx_hash}: {e}")
            return None

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get transaction confirmation count."""
        try:
            from solders.signature import Signature

            signature = Signature.from_string(tx_hash)

            # Get transaction status
            response = await self._client.get_signature_statuses([signature])
            if not response.value or not response.value[0]:
                return 0

            status = response.value[0]
            if status.confirmations is not None:
                return status.confirmations

            # If confirmations is None but confirmed, return max confirmations
            if status.confirmation_status and str(status.confirmation_status) == "finalized":
                return self.required_confirmations

            return 0

        except Exception as e:
            logger.error(f"Failed to get confirmations for {tx_hash}: {e}")
            return 0

    async def close(self):
        """Close the client connection."""
        try:
            await self._client.close()
        except Exception:
            pass
