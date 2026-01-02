"""AKX Crypto Payment Gateway - TRON chain scanner.

Scans TRON blockchain for TRC20 token deposits.
Uses TronGrid API for transaction history.

Payment method is uniquely identified by: chain + token
"""

import logging
from decimal import Decimal

import httpx

from src.celery_app import celery_app
from src.core.config import get_settings
from src.models.order import Order
from src.models.wallet import TOKEN_CONTRACTS, Chain, Token, get_token_decimals
from src.workers.chain_scanners.base_scanner import BaseChainScanner, DepositMatch

logger = logging.getLogger(__name__)


class TronScanner(BaseChainScanner):
    """TRON blockchain scanner for TRC20 deposits.

    Uses TronGrid API to scan for token transfers.
    TRON requires 19 confirmations for finality.

    Supports multiple tokens: USDT, USDC, etc.
    """

    chain = Chain.TRON
    required_confirmations = 19

    def __init__(self):
        super().__init__()
        self._settings = get_settings()
        self._network = self._settings.tron_network

        # Set API base URL
        if self._network == "mainnet":
            self._api_base = "https://api.trongrid.io"
        else:
            self._api_base = f"https://api.{self._network}.trongrid.io"

        # Load token contracts from config
        self.token_contracts = TOKEN_CONTRACTS.get(Chain.TRON, {})

        # API key for TronGrid
        self._api_key = self._settings.tron_api_key

    def _get_headers(self) -> dict:
        """Get HTTP headers with API key."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["TRON-PRO-API-KEY"] = self._api_key
        return headers

    async def get_current_block_number(self) -> int:
        """Get current TRON block number."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._api_base}/wallet/getnowblock",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()
            return data["block_header"]["raw_data"]["number"]

    async def scan_block_for_deposits(
        self,
        block_number: int,
        pending_orders: list[Order],
    ) -> list[DepositMatch]:
        """Scan a TRON block for TRC20 deposits.

        For efficiency, we scan by address rather than by block.
        This method fetches TRC20 transfers for each pending order's wallet.
        Matches are based on: wallet_address + token + amount
        """
        matches = []

        # Group orders by wallet address and token
        address_token_orders: dict[tuple[str, str], list[Order]] = {}
        for order in pending_orders:
            key = (order.wallet_address, order.token)
            if key not in address_token_orders:
                address_token_orders[key] = []
            address_token_orders[key].append(order)

        # Scan each address+token combination
        for (address, token_str), orders in address_token_orders.items():
            try:
                # Get token enum and contract
                token = Token(token_str)
                contract_address = self.token_contracts.get(token)
                if not contract_address:
                    logger.warning(f"No contract for {token.value} on TRON")
                    continue

                transfers = await self._get_trc20_transfers(address, contract_address)
                for transfer in transfers:
                    match = self._match_transfer_to_order(transfer, orders, block_number, token)
                    if match:
                        matches.append(match)
            except Exception as e:
                logger.error(f"Error scanning address {address} for {token_str}: {e}")

        return matches

    async def _get_trc20_transfers(
        self,
        address: str,
        contract_address: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get TRC20 transfers to an address for a specific token contract."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._api_base}/v1/accounts/{address}/transactions/trc20",
                params={
                    "contract_address": contract_address,
                    "only_to": "true",
                    "limit": limit,
                },
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

    def _match_transfer_to_order(
        self,
        transfer: dict,
        orders: list[Order],
        current_block: int,
        token: Token,
    ) -> DepositMatch | None:
        """Match a TRC20 transfer to a pending order."""
        tx_hash = transfer.get("transaction_id")
        value = int(transfer.get("value", 0))
        decimals = get_token_decimals(token)
        amount = Decimal(str(value)) / Decimal(10**decimals)
        block_number = transfer.get("block_timestamp", 0)
        from_address = transfer.get("from")

        # Find matching order by amount (orders already filtered by token)
        for order in orders:
            # Check if amount matches (with small tolerance for rounding)
            if abs(amount - order.amount) < Decimal("0.000001"):
                # Verify this tx hasn't been processed already
                if order.tx_hash and order.tx_hash == tx_hash:
                    continue

                confirmations = max(0, current_block - block_number)

                return DepositMatch(
                    order=order,
                    tx_hash=tx_hash,
                    amount=amount,
                    token=token,
                    confirmations=confirmations,
                    block_number=block_number,
                    from_address=from_address,
                    raw_data=transfer,
                )

        return None

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get confirmation count for a TRON transaction."""
        async with httpx.AsyncClient() as client:
            # Get transaction info
            response = await client.post(
                f"{self._api_base}/wallet/gettransactioninfobyid",
                json={"value": tx_hash},
                headers=self._get_headers(),
            )
            response.raise_for_status()
            tx_info = response.json()

            if not tx_info:
                return 0

            tx_block = tx_info.get("blockNumber", 0)
            if not tx_block:
                return 0

            # Get current block
            current_block = await self.get_current_block_number()
            return max(0, current_block - tx_block)


# Singleton scanner instance
_tron_scanner: TronScanner | None = None


def get_tron_scanner() -> TronScanner:
    """Get singleton TRON scanner instance."""
    global _tron_scanner
    if _tron_scanner is None:
        _tron_scanner = TronScanner()
    return _tron_scanner


# ============ Celery Tasks ============


@celery_app.task(name="src.workers.chain_scanners.tron_scanner.scan_tron_blocks")
def scan_tron_blocks():
    """Celery task to scan TRON blocks for deposits.

    This task runs in its own process/queue for TRON.
    """
    import asyncio

    scanner = get_tron_scanner()

    # Run async scan in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.scan_blocks())
        logger.info(f"TRON scan complete: {result}")
        return result
    finally:
        loop.close()


@celery_app.task(name="src.workers.chain_scanners.tron_scanner.update_tron_confirmations")
def update_tron_confirmations():
    """Update confirmation counts for TRON orders."""
    import asyncio

    scanner = get_tron_scanner()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.update_confirmations())
        logger.info(f"TRON confirmations updated: {result}")
        return result
    finally:
        loop.close()
