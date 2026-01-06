"""Fund Collection Service - Execute fund collection from recharge addresses to hot wallet.

This service handles:
1. Collection task execution - Transfer funds from recharge addresses to hot wallet
2. Gas optimization - Use TRON energy mechanism for near-zero gas fees
3. Batch collection - Process multiple addresses in batches
4. Error handling and retry - Handle failed transfers with retry logic
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.core.security import get_cipher
from src.models.chain import Chain
from src.models.recharge import (
    CollectTask,
    CollectTaskStatus,
    RechargeAddress,
    RechargeAddressStatus,
)
from src.models.token import Token
from src.models.wallet import Wallet
from src.services.tron_service import TronService, get_tron_service

logger = logging.getLogger(__name__)


class CollectService:
    """Service for fund collection operations."""

    # Collection thresholds
    MIN_COLLECT_AMOUNT = Decimal("10")  # Minimum USDT to trigger collection
    MAX_GAS_RATIO = Decimal("0.05")  # Max 5% of amount for gas

    # Batch settings
    BATCH_SIZE = 10  # Max addresses per batch
    BATCH_DELAY = 2  # Seconds between transfers

    def __init__(self, db: AsyncSession, tron_service: TronService | None = None):
        self.db = db
        self.settings = get_settings()
        self.cipher = get_cipher()
        self.tron = tron_service or get_tron_service()

    # ============ Collection Task Management ============

    async def scan_and_create_tasks(
        self,
        hot_wallet_id: int,
        chain_code: str = "tron",
        token_code: str = "USDT",
    ) -> list[CollectTask]:
        """Scan recharge addresses and create collection tasks for eligible ones.

        Args:
            hot_wallet_id: Destination hot wallet ID
            chain_code: Blockchain network
            token_code: Token code

        Returns:
            List of created tasks
        """
        # Get chain and token
        chain = await self._get_chain(chain_code)
        token = await self._get_token(token_code)

        if not chain or not token:
            logger.error(f"Chain {chain_code} or token {token_code} not found")
            return []

        # Get hot wallet
        hot_wallet = await self.db.get(Wallet, hot_wallet_id)
        if not hot_wallet:
            logger.error(f"Hot wallet {hot_wallet_id} not found")
            return []

        # Find assigned recharge addresses
        query = select(RechargeAddress).where(
            RechargeAddress.chain_id == chain.id,
            RechargeAddress.token_id == token.id,
            RechargeAddress.status == RechargeAddressStatus.ASSIGNED,
        )

        # Exclude addresses with pending/processing tasks
        pending_subquery = select(CollectTask.recharge_address_id).where(
            CollectTask.status.in_([CollectTaskStatus.PENDING, CollectTaskStatus.PROCESSING])
        )
        query = query.where(RechargeAddress.id.notin_(pending_subquery))

        result = await self.db.execute(query)
        addresses = result.scalars().all()

        created_tasks: list[CollectTask] = []

        for addr in addresses:
            if not addr.wallet:
                continue

            # Check actual on-chain balance
            balance = await self.tron.get_usdt_balance(addr.wallet.address)

            if balance < self.MIN_COLLECT_AMOUNT:
                logger.debug(f"Address {addr.wallet.address} balance {balance} below threshold")
                continue

            # Create collection task
            task = CollectTask(
                recharge_address_id=addr.id,
                hot_wallet_id=hot_wallet_id,
                chain_id=chain.id,
                token_id=token.id,
                amount=balance,
                status=CollectTaskStatus.PENDING,
            )
            self.db.add(task)
            created_tasks.append(task)
            logger.info(f"Created collect task for {addr.wallet.address}, amount: {balance}")

        await self.db.commit()
        return created_tasks

    async def execute_pending_tasks(
        self,
        chain_code: str = "tron",
        max_tasks: int = 10,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute pending collection tasks.

        Args:
            chain_code: Blockchain network
            max_tasks: Maximum tasks to execute
            dry_run: If True, don't actually execute transfers

        Returns:
            Execution summary
        """
        chain = await self._get_chain(chain_code)
        if not chain:
            return {"error": f"Chain {chain_code} not found"}

        # Get pending tasks
        query = (
            select(CollectTask)
            .where(
                CollectTask.chain_id == chain.id,
                CollectTask.status == CollectTaskStatus.PENDING,
            )
            .order_by(CollectTask.created_at)
            .limit(max_tasks)
        )

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        if not tasks:
            return {"message": "No pending tasks", "executed": 0}

        results = {
            "total": len(tasks),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        for task in tasks:
            task_result = await self._execute_single_task(task, dry_run=dry_run)
            results["details"].append(task_result)

            if task_result["status"] == "success":
                results["success"] += 1
            elif task_result["status"] == "failed":
                results["failed"] += 1
            else:
                results["skipped"] += 1

            # Delay between transfers
            if not dry_run:
                await asyncio.sleep(self.BATCH_DELAY)

        await self.db.commit()
        return results

    async def _execute_single_task(
        self,
        task: CollectTask,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a single collection task.

        Args:
            task: Collection task to execute
            dry_run: If True, don't actually execute transfer

        Returns:
            Task execution result
        """
        if not task.recharge_address or not task.recharge_address.wallet:
            task.status = CollectTaskStatus.SKIPPED
            task.error_message = "No wallet found for recharge address"
            return {"task_id": task.id, "status": "skipped", "error": task.error_message}

        if not task.hot_wallet:
            task.status = CollectTaskStatus.SKIPPED
            task.error_message = "No hot wallet found"
            return {"task_id": task.id, "status": "skipped", "error": task.error_message}

        from_address = task.recharge_address.wallet.address
        to_address = task.hot_wallet.address
        amount = task.amount

        # Re-check balance
        current_balance = await self.tron.get_usdt_balance(from_address)
        if current_balance < self.MIN_COLLECT_AMOUNT:
            task.status = CollectTaskStatus.SKIPPED
            task.error_message = f"Balance {current_balance} below threshold"
            return {
                "task_id": task.id,
                "status": "skipped",
                "error": task.error_message,
                "balance": str(current_balance),
            }

        # Use actual balance instead of recorded amount
        amount = current_balance

        if dry_run:
            return {
                "task_id": task.id,
                "status": "dry_run",
                "from": from_address,
                "to": to_address,
                "amount": str(amount),
            }

        # Mark as processing
        task.status = CollectTaskStatus.PROCESSING
        from datetime import datetime

        task.executed_at = datetime.utcnow()
        await self.db.flush()

        try:
            # Decrypt private key
            encrypted_key = task.recharge_address.wallet.encrypted_private_key
            private_key = self.cipher.decrypt(encrypted_key)

            # Execute transfer
            tx_hash = await self._execute_trc20_transfer(
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                private_key=private_key,
            )

            if tx_hash:
                task.status = CollectTaskStatus.SUCCESS
                task.tx_hash = tx_hash
                task.amount = amount
                task.completed_at = datetime.utcnow()

                return {
                    "task_id": task.id,
                    "status": "success",
                    "tx_hash": tx_hash,
                    "amount": str(amount),
                }
            else:
                task.status = CollectTaskStatus.FAILED
                task.error_message = "Transfer failed"
                task.retry_count += 1

                return {
                    "task_id": task.id,
                    "status": "failed",
                    "error": "Transfer execution failed",
                }

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}")
            task.status = CollectTaskStatus.FAILED
            task.error_message = str(e)[:500]
            task.retry_count += 1

            return {
                "task_id": task.id,
                "status": "failed",
                "error": str(e),
            }

    async def _execute_trc20_transfer(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        private_key: str,
    ) -> str | None:
        """Execute TRC20 USDT transfer.

        Args:
            from_address: Source address
            to_address: Destination address
            amount: Amount to transfer
            private_key: Sender's private key

        Returns:
            Transaction hash or None on failure
        """
        try:
            # Use tronpy for local signing (recommended for security)
            from tronpy import Tron
            from tronpy.keys import PrivateKey

            # Connect to network
            if self.settings.tron_network == "mainnet":
                client = Tron()
            else:
                client = Tron(network=self.settings.tron_network)

            if self.settings.tron_api_key:
                client = Tron(
                    network=self.settings.tron_network
                    if self.settings.tron_network != "mainnet"
                    else None,
                )

            # Get contract
            contract = client.get_contract(self.tron.USDT_CONTRACT)

            # Convert amount to raw
            amount_raw = int(amount * Decimal(10**6))

            # Build transaction
            txn = (
                contract.functions.transfer(to_address, amount_raw)
                .with_owner(from_address)
                .fee_limit(100_000_000)  # 100 TRX max
                .build()
            )

            # Sign with private key
            priv_key = PrivateKey(bytes.fromhex(private_key))
            signed_txn = txn.sign(priv_key)

            # Broadcast
            result = signed_txn.broadcast()

            if result.get("result"):
                tx_hash = result.get("txid")
                logger.info(f"Transfer successful: {tx_hash}")
                return tx_hash
            else:
                logger.error(f"Transfer failed: {result}")
                return None

        except ImportError:
            logger.error("tronpy not installed. Run: uv add tronpy")
            return None

        except Exception as e:
            logger.error(f"Transfer error: {e}")
            return None

    async def retry_failed_tasks(
        self,
        chain_code: str = "tron",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Retry failed collection tasks.

        Args:
            chain_code: Blockchain network
            max_retries: Maximum retry count

        Returns:
            Retry summary
        """
        chain = await self._get_chain(chain_code)
        if not chain:
            return {"error": f"Chain {chain_code} not found"}

        # Get failed tasks with retries remaining
        query = select(CollectTask).where(
            CollectTask.chain_id == chain.id,
            CollectTask.status == CollectTaskStatus.FAILED,
            CollectTask.retry_count < max_retries,
        )

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        # Reset status to pending
        for task in tasks:
            task.status = CollectTaskStatus.PENDING
            task.error_message = None

        await self.db.commit()

        return {
            "message": f"Reset {len(tasks)} failed tasks to pending",
            "count": len(tasks),
        }

    # ============ Statistics ============

    async def get_collection_stats(
        self,
        chain_code: str = "tron",
    ) -> dict[str, Any]:
        """Get collection statistics.

        Args:
            chain_code: Blockchain network

        Returns:
            Collection statistics
        """
        from sqlalchemy import func

        chain = await self._get_chain(chain_code)
        if not chain:
            return {"error": f"Chain {chain_code} not found"}

        # Count by status
        status_query = (
            select(
                CollectTask.status,
                func.count(CollectTask.id),
                func.sum(CollectTask.amount),
            )
            .where(CollectTask.chain_id == chain.id)
            .group_by(CollectTask.status)
        )

        result = await self.db.execute(status_query)
        rows = result.all()

        stats = {
            "chain": chain_code,
            "by_status": {},
            "total_tasks": 0,
            "total_collected": Decimal("0"),
        }

        for status, count, total_amount in rows:
            stats["by_status"][status.value] = {
                "count": count,
                "amount": str(total_amount or 0),
            }
            stats["total_tasks"] += count
            if status == CollectTaskStatus.SUCCESS:
                stats["total_collected"] = total_amount or Decimal("0")

        stats["total_collected"] = str(stats["total_collected"])
        return stats

    # ============ Helper Methods ============

    async def _get_chain(self, code: str) -> Chain | None:
        """Get chain by code."""
        from sqlalchemy import func

        result = await self.db.execute(select(Chain).where(func.lower(Chain.code) == code.lower()))
        return result.scalar_one_or_none()

    async def _get_token(self, code: str) -> Token | None:
        """Get token by code."""
        from sqlalchemy import func

        result = await self.db.execute(select(Token).where(func.upper(Token.code) == code.upper()))
        return result.scalar_one_or_none()
