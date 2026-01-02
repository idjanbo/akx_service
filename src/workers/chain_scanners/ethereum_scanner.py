"""AKX Crypto Payment Gateway - Ethereum chain scanner.

Scans Ethereum blockchain for USDT-ERC20 deposits.
Uses JSON-RPC or Etherscan API.
"""

import logging
from decimal import Decimal

from src.celery_app import celery_app
from src.core.config import get_settings
from src.models.order import Order
from src.models.wallet import Chain
from src.workers.chain_scanners.base_scanner import BaseChainScanner, DepositMatch

logger = logging.getLogger(__name__)


class EthereumScanner(BaseChainScanner):
    """Ethereum blockchain scanner for ERC20 deposits.

    Uses web3.py to scan for USDT transfers.
    Ethereum requires 12 confirmations for finality.
    """

    chain = Chain.ETHEREUM
    required_confirmations = 12

    # USDT-ERC20 mainnet contract
    USDT_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

    def __init__(self):
        super().__init__()
        self._settings = get_settings()
        self._rpc_url = self._settings.eth_rpc_url
        self.usdt_contract = self.USDT_CONTRACT

    async def get_current_block_number(self) -> int:
        """Get current Ethereum block number."""
        try:
            from web3 import AsyncHTTPProvider, AsyncWeb3

            w3 = AsyncWeb3(AsyncHTTPProvider(self._rpc_url))
            return await w3.eth.block_number
        except ImportError:
            logger.warning("web3 not installed, skipping Ethereum scan")
            return 0
        except Exception as e:
            logger.error(f"Failed to get ETH block number: {e}")
            return 0

    async def scan_block_for_deposits(
        self,
        block_number: int,
        pending_orders: list[Order],
    ) -> list[DepositMatch]:
        """Scan an Ethereum block for ERC20 deposits.

        Note: Full implementation requires scanning Transfer events
        from the USDT contract.
        """
        matches = []

        try:
            from web3 import AsyncHTTPProvider, AsyncWeb3

            w3 = AsyncWeb3(AsyncHTTPProvider(self._rpc_url))

            # ERC20 Transfer event signature
            transfer_topic = w3.keccak(text="Transfer(address,address,uint256)").hex()

            # Get logs for USDT transfers in this block
            logs = await w3.eth.get_logs(
                {
                    "fromBlock": block_number,
                    "toBlock": block_number,
                    "address": self.usdt_contract,
                    "topics": [transfer_topic],
                }
            )

            # Group orders by wallet address (lowercase for ETH)
            address_orders: dict[str, list[Order]] = {}
            for order in pending_orders:
                addr = order.wallet_address.lower()
                if addr not in address_orders:
                    address_orders[addr] = []
                address_orders[addr].append(order)

            current_block = await self.get_current_block_number()

            for log in logs:
                # Decode transfer: from (topic[1]), to (topic[2]), amount (data)
                if len(log["topics"]) < 3:
                    continue

                to_address = "0x" + log["topics"][2].hex()[-40:]
                to_address = to_address.lower()

                if to_address in address_orders:
                    # Decode amount (USDT has 6 decimals)
                    amount_raw = int(log["data"].hex(), 16)
                    amount = Decimal(str(amount_raw)) / Decimal("1000000")

                    from_address = "0x" + log["topics"][1].hex()[-40:]
                    tx_hash = log["transactionHash"].hex()

                    for order in address_orders[to_address]:
                        if abs(amount - order.amount) < Decimal("0.000001"):
                            confirmations = max(0, current_block - block_number)
                            matches.append(
                                DepositMatch(
                                    order=order,
                                    tx_hash=tx_hash,
                                    amount=amount,
                                    confirmations=confirmations,
                                    block_number=block_number,
                                    from_address=from_address,
                                )
                            )
                            break

        except ImportError:
            logger.warning("web3 not installed, skipping Ethereum scan")
        except Exception as e:
            logger.error(f"Error scanning ETH block {block_number}: {e}")

        return matches

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get confirmation count for an Ethereum transaction."""
        try:
            from web3 import AsyncHTTPProvider, AsyncWeb3

            w3 = AsyncWeb3(AsyncHTTPProvider(self._rpc_url))

            receipt = await w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or not receipt["blockNumber"]:
                return 0

            current_block = await self.get_current_block_number()
            return max(0, current_block - receipt["blockNumber"])

        except ImportError:
            return 0
        except Exception as e:
            logger.error(f"Failed to get ETH tx confirmations: {e}")
            return 0


# Singleton scanner instance
_eth_scanner: EthereumScanner | None = None


def get_ethereum_scanner() -> EthereumScanner:
    """Get singleton Ethereum scanner instance."""
    global _eth_scanner
    if _eth_scanner is None:
        _eth_scanner = EthereumScanner()
    return _eth_scanner


# ============ Celery Tasks ============


@celery_app.task(name="src.workers.chain_scanners.ethereum_scanner.scan_ethereum_blocks")
def scan_ethereum_blocks():
    """Celery task to scan Ethereum blocks for deposits."""
    import asyncio

    scanner = get_ethereum_scanner()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.scan_blocks())
        logger.info(f"Ethereum scan complete: {result}")
        return result
    finally:
        loop.close()


@celery_app.task(name="src.workers.chain_scanners.ethereum_scanner.update_ethereum_confirmations")
def update_ethereum_confirmations():
    """Update confirmation counts for Ethereum orders."""
    import asyncio

    scanner = get_ethereum_scanner()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scanner.update_confirmations())
        logger.info(f"Ethereum confirmations updated: {result}")
        return result
    finally:
        loop.close()
