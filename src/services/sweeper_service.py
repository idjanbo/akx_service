"""AKX Crypto Payment Gateway - Fund sweeper worker.

Collects funds from deposit wallets to cold storage.
Handles gas fee provisioning for deposit wallets.
Called by Celery tasks on a schedule.
"""

import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.chains import get_chain
from src.core.security import decrypt_private_key
from src.db import get_session
from src.models.wallet import Chain, Wallet, WalletType

logger = logging.getLogger(__name__)


class SweeperService:
    """Fund sweeper for collecting deposits to cold storage.

    Provides methods for one-shot sweeping, designed to be called
    by Celery tasks on a schedule.

    Workflow:
    1. Find deposit wallets with USDT balance
    2. Check if wallet has enough native token (TRX/ETH) for gas
    3. If no gas, transfer from gas wallet
    4. Sweep USDT to cold wallet

    Usage (via Celery common_tasks.py):
        sweeper = Sweeper()
        result = await sweeper.sweep_once()
    """

    # Minimum USDT balance to trigger sweep
    MIN_SWEEP_AMOUNT = Decimal("10.0")

    # Gas requirements per chain (approximate)
    GAS_REQUIREMENTS = {
        Chain.TRON: Decimal("15.0"),  # TRX for TRC20 transfer
        Chain.ETHEREUM: Decimal("0.005"),  # ETH for ERC20 transfer
        Chain.SOLANA: Decimal("0.01"),  # SOL for SPL transfer
    }

    def __init__(self, chains: list[Chain] | None = None) -> None:
        """Initialize sweeper.

        Args:
            chains: Chains to sweep (default: TRON only)
        """
        self._chains = chains or [Chain.TRON]

    async def sweep_once(self) -> dict:
        """Perform a single sweep cycle across all chains.

        Returns:
            Dict with sweep statistics
        """
        wallets_processed = 0
        usdt_swept = Decimal("0")
        gas_sent = 0

        for chain in self._chains:
            try:
                result = await self._sweep_chain(chain)
                wallets_processed += result["wallets_processed"]
                usdt_swept += result["usdt_swept"]
                gas_sent += result["gas_sent"]
            except Exception as e:
                logger.error(f"Error sweeping {chain.value}: {e}", exc_info=True)

        return {
            "wallets_processed": wallets_processed,
            "usdt_swept": usdt_swept,
            "gas_sent": gas_sent,
        }

    async def _sweep_chain(self, chain: Chain) -> dict:
        """Sweep funds for a specific chain.

        Args:
            chain: Blockchain to sweep

        Returns:
            Dict with chain sweep statistics
        """
        wallets_processed = 0
        usdt_swept = Decimal("0")
        gas_sent = 0

        async with get_session() as db:
            # Get cold wallet for this chain
            cold_wallet = await self._get_system_wallet(db, chain, WalletType.COLD)
            if not cold_wallet:
                logger.warning(f"No cold wallet configured for {chain.value}")
                return {"wallets_processed": 0, "usdt_swept": Decimal("0"), "gas_sent": 0}

            # Get gas wallet for this chain
            gas_wallet = await self._get_system_wallet(db, chain, WalletType.GAS)
            if not gas_wallet:
                logger.warning(f"No gas wallet configured for {chain.value}")
                return {"wallets_processed": 0, "usdt_swept": Decimal("0"), "gas_sent": 0}

            # Get all deposit wallets
            result = await db.execute(
                select(Wallet).where(
                    Wallet.chain == chain,
                    Wallet.wallet_type == WalletType.DEPOSIT,
                    Wallet.is_active == True,  # noqa: E712
                )
            )
            deposit_wallets = result.scalars().all()

            chain_impl = get_chain(chain)

            for wallet in deposit_wallets:
                try:
                    process_result = await self._process_wallet(
                        wallet,
                        cold_wallet,
                        gas_wallet,
                        chain_impl,
                        chain,
                    )
                    if process_result["processed"]:
                        wallets_processed += 1
                    if process_result["swept"]:
                        usdt_swept += process_result["swept"]
                    if process_result["gas_sent"]:
                        gas_sent += 1
                except Exception as e:
                    logger.error(f"Error processing wallet {wallet.address}: {e}")

        return {
            "wallets_processed": wallets_processed,
            "usdt_swept": usdt_swept,
            "gas_sent": gas_sent,
        }

    async def _process_wallet(
        self,
        wallet: Wallet,
        cold_wallet: Wallet,
        gas_wallet: Wallet,
        chain_impl,
        chain: Chain,
    ) -> dict:
        """Process a single deposit wallet for sweeping.

        Returns:
            Dict with processing results
        """
        result = {"processed": False, "swept": Decimal("0"), "gas_sent": False}

        # Check wallet balance
        balance = await chain_impl.get_balance(wallet.address)

        # Skip if USDT balance below threshold
        if balance.usdt_balance < self.MIN_SWEEP_AMOUNT:
            return result

        result["processed"] = True
        logger.info(
            f"Sweeping wallet {wallet.address}: "
            f"{balance.usdt_balance} USDT, {balance.native_balance} native"
        )

        # Check if wallet needs gas
        gas_required = self.GAS_REQUIREMENTS.get(chain, Decimal("0"))
        if balance.native_balance < gas_required:
            gas_success = await self._provision_gas(
                gas_wallet,
                wallet,
                gas_required - balance.native_balance,
                chain_impl,
            )
            result["gas_sent"] = gas_success
            # Wait for gas transaction to confirm before sweeping
            return result

        # Execute USDT sweep
        swept = await self._execute_sweep(
            wallet,
            cold_wallet,
            balance.usdt_balance,
            chain_impl,
        )
        result["swept"] = swept

        return result

    async def _provision_gas(
        self,
        gas_wallet: Wallet,
        target_wallet: Wallet,
        amount: Decimal,
        chain_impl,
    ) -> bool:
        """Send gas to a wallet that needs it.

        Returns:
            True if gas was sent successfully
        """
        logger.info(f"Provisioning {amount} gas to {target_wallet.address}")

        # Decrypt gas wallet private key
        private_key = decrypt_private_key(gas_wallet.encrypted_private_key)

        try:
            result = await chain_impl.transfer_native(
                from_address=gas_wallet.address,
                to_address=target_wallet.address,
                amount=amount,
                private_key=private_key,
            )

            if result.success:
                logger.info(f"Gas provisioned: tx={result.tx_hash}")
                return True
            else:
                logger.error(f"Gas provision failed: {result.error_message}")
                return False

        finally:
            # Clear private key from memory
            del private_key

    async def _execute_sweep(
        self,
        source_wallet: Wallet,
        cold_wallet: Wallet,
        amount: Decimal,
        chain_impl,
    ) -> Decimal:
        """Sweep USDT from source to cold wallet.

        Returns:
            Amount swept, or 0 if failed
        """
        logger.info(f"Sweeping {amount} USDT from {source_wallet.address}")

        # Decrypt source wallet private key
        private_key = decrypt_private_key(source_wallet.encrypted_private_key)

        try:
            result = await chain_impl.transfer_usdt(
                from_address=source_wallet.address,
                to_address=cold_wallet.address,
                amount=amount,
                private_key=private_key,
            )

            if result.success:
                logger.info(f"Sweep complete: tx={result.tx_hash}")
                return amount
            else:
                logger.error(f"Sweep failed: {result.error_message}")
                return Decimal("0")

        finally:
            # Clear private key from memory
            del private_key

    async def _get_system_wallet(
        self,
        db: AsyncSession,
        chain: Chain,
        wallet_type: WalletType,
    ) -> Wallet | None:
        """Get system wallet (gas or cold) for a chain."""
        result = await db.execute(
            select(Wallet).where(
                Wallet.chain == chain,
                Wallet.wallet_type == wallet_type,
                Wallet.user_id == None,  # noqa: E711
                Wallet.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()
