"""AKX Crypto Payment Gateway - Solana chain scanner.

Scans Solana blockchain for USDT-SPL deposits.
Uses Solana JSON-RPC API.
"""

import logging
from decimal import Decimal

import httpx

from src.celery_app import celery_app
from src.core.config import get_settings
from src.models.order import Order
from src.models.wallet import Chain
from src.workers.chain_scanners.base_scanner import BaseChainScanner, DepositMatch

logger = logging.getLogger(__name__)


class SolanaScanner(BaseChainScanner):
    """Solana blockchain scanner for SPL token deposits.

    Uses solana-py to scan for USDT transfers.
    Solana has fast finality (~1-2 seconds).
    """

    chain = Chain.SOLANA
    required_confirmations = 32  # Solana slots for finality

    # USDT SPL token mint address (mainnet)
    USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

    def __init__(self):
        super().__init__()
        self._settings = get_settings()
        self._rpc_url = self._settings.solana_rpc_url
        self.usdt_contract = self.USDT_MINT

    async def get_current_block_number(self) -> int:
        """Get current Solana slot number."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getSlot",
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("result", 0)

        except Exception as e:
            logger.error(f"Failed to get Solana slot: {e}")
            return 0

    async def scan_block_for_deposits(
        self,
        block_number: int,
        pending_orders: list[Order],
    ) -> list[DepositMatch]:
        """Scan Solana for SPL token deposits.

        Note: Solana scanning is different - we scan by signature history
        for each address rather than by block.
        """
        matches = []

        try:
            # Group orders by wallet address
            address_orders: dict[str, list[Order]] = {}
            for order in pending_orders:
                addr = order.wallet_address
                if addr not in address_orders:
                    address_orders[addr] = []
                address_orders[addr].append(order)

            current_slot = await self.get_current_block_number()

            async with httpx.AsyncClient() as client:
                for address, orders in address_orders.items():
                    try:
                        # Get recent signatures for the address
                        response = await client.post(
                            self._rpc_url,
                            json={
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "getSignaturesForAddress",
                                "params": [address, {"limit": 20}],
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                        signatures = data.get("result", [])

                        for sig_info in signatures:
                            sig = sig_info.get("signature")
                            slot = sig_info.get("slot", 0)

                            # Get transaction details
                            tx_match = await self._check_transaction(
                                client, sig, orders, address, slot, current_slot
                            )
                            if tx_match:
                                matches.append(tx_match)

                    except Exception as e:
                        logger.error(f"Error scanning Solana address {address}: {e}")

        except Exception as e:
            logger.error(f"Solana scan error: {e}")

        return matches

    async def _check_transaction(
        self,
        client: httpx.AsyncClient,
        signature: str,
        orders: list[Order],
        address: str,
        slot: int,
        current_slot: int,
    ) -> DepositMatch | None:
        """Check if a transaction is a matching deposit."""
        try:
            response = await client.post(
                self._rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [
                        signature,
                        {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            tx = data.get("result")

            if not tx:
                return None

            # Parse token transfers from inner instructions
            meta = tx.get("meta", {})
            if meta.get("err"):
                return None

            # Check post token balances
            post_balances = meta.get("postTokenBalances", [])
            pre_balances = meta.get("preTokenBalances", [])

            for i, post in enumerate(post_balances):
                if post.get("mint") != self.USDT_MINT:
                    continue

                owner = post.get("owner")
                if owner != address:
                    continue

                # Calculate transfer amount
                post_amount = Decimal(post.get("uiTokenAmount", {}).get("uiAmountString", "0"))
                pre_amount = Decimal("0")

                for pre in pre_balances:
                    if pre.get("accountIndex") == post.get("accountIndex"):
                        pre_amount = Decimal(
                            pre.get("uiTokenAmount", {}).get("uiAmountString", "0")
                        )
                        break

                received = post_amount - pre_amount

                if received > 0:
                    # Match to order
                    for order in orders:
                        if abs(received - order.amount) < Decimal("0.000001"):
                            confirmations = max(0, current_slot - slot)
                            return DepositMatch(
                                order=order,
                                tx_hash=signature,
                                amount=received,
                                confirmations=confirmations,
                                block_number=slot,
                            )

        except Exception as e:
            logger.error(f"Error checking Solana tx {signature}: {e}")

        return None

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get confirmation count for a Solana transaction."""
        try:
            async with httpx.AsyncClient() as client:
                # Get transaction status
                response = await client.post(
                    self._rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [tx_hash, {"encoding": "jsonParsed"}],
                    },
                )
                response.raise_for_status()
                data = response.json()
                tx = data.get("result")

                if not tx:
                    return 0

                slot = tx.get("slot", 0)
                current_slot = await self.get_current_block_number()
                return max(0, current_slot - slot)

        except Exception as e:
            logger.error(f"Failed to get Solana tx confirmations: {e}")
            return 0


# Singleton scanner instance
_solana_scanner: SolanaScanner | None = None


def get_solana_scanner() -> SolanaScanner:
    """Get singleton Solana scanner instance."""
    global _solana_scanner
    if _solana_scanner is None:
        _solana_scanner = SolanaScanner()
    return _solana_scanner


# ============ Celery Tasks ============


@celery_app.task(name="src.workers.chain_scanners.solana_scanner.scan_solana_blocks")
def scan_solana_blocks():
    """Celery task to scan Solana for deposits."""
    import asyncio

    scanner = get_solana_scanner()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.scan_blocks())
        logger.info(f"Solana scan complete: {result}")
        return result
    finally:
        loop.close()


@celery_app.task(name="src.workers.chain_scanners.solana_scanner.update_solana_confirmations")
def update_solana_confirmations():
    """Update confirmation counts for Solana orders."""
    import asyncio

    scanner = get_solana_scanner()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.update_confirmations())
        logger.info(f"Solana confirmations updated: {result}")
        return result
    finally:
        loop.close()
