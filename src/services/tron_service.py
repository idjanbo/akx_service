"""TRON Blockchain Service - Interact with TRON network.

This service handles:
1. Balance queries - Check TRX and TRC20 token balances
2. Transaction monitoring - Watch for incoming deposits
3. Transaction execution - Send TRC20 transfers for fund collection
4. Energy/Bandwidth management - Optimize gas costs
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class TronService:
    """Service for TRON blockchain interactions."""

    # USDT TRC20 contract address (mainnet)
    USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    # USDT decimals
    USDT_DECIMALS = 6

    # Required confirmations
    REQUIRED_CONFIRMATIONS = 19

    # API endpoints by network
    API_ENDPOINTS = {
        "mainnet": "https://api.trongrid.io",
        "shasta": "https://api.shasta.trongrid.io",
        "nile": "https://nile.trongrid.io",
    }

    def __init__(self):
        self.settings = get_settings()
        self.network = self.settings.tron_network
        self.api_key = self.settings.tron_api_key
        self.base_url = self.API_ENDPOINTS.get(self.network, self.API_ENDPOINTS["mainnet"])
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                headers["TRON-PRO-API-KEY"] = self.api_key
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ============ Balance Queries ============

    async def get_trx_balance(self, address: str) -> Decimal:
        """Get TRX balance for an address.

        Args:
            address: TRON address (base58)

        Returns:
            Balance in TRX (not sun)
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/v1/accounts/{address}")
            response.raise_for_status()
            data = response.json()

            if not data.get("data"):
                return Decimal("0")

            balance_sun = data["data"][0].get("balance", 0)
            return Decimal(balance_sun) / Decimal("1000000")  # Sun to TRX

        except Exception as e:
            logger.error(f"Failed to get TRX balance for {address}: {e}")
            return Decimal("0")

    async def get_usdt_balance(self, address: str) -> Decimal:
        """Get USDT (TRC20) balance for an address.

        Args:
            address: TRON address (base58)

        Returns:
            Balance in USDT
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"/v1/accounts/{address}/tokens",
                params={"only_trc20": "true"},
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("data"):
                return Decimal("0")

            # Find USDT token
            for token in data["data"]:
                if token.get("token_id") == self.USDT_CONTRACT:
                    balance_raw = int(token.get("balance", 0))
                    return Decimal(balance_raw) / Decimal(10**self.USDT_DECIMALS)

            return Decimal("0")

        except Exception as e:
            logger.error(f"Failed to get USDT balance for {address}: {e}")
            return Decimal("0")

    async def get_account_resources(self, address: str) -> dict[str, Any]:
        """Get account resources (bandwidth, energy).

        Args:
            address: TRON address

        Returns:
            Resource information including energy and bandwidth
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/v1/accounts/{address}/resources")
            response.raise_for_status()
            data = response.json()

            if not data.get("data"):
                return {"energy": 0, "bandwidth": 0}

            resources = data["data"]
            return {
                "energy_limit": resources.get("EnergyLimit", 0),
                "energy_used": resources.get("EnergyUsed", 0),
                "energy_available": resources.get("EnergyLimit", 0)
                - resources.get("EnergyUsed", 0),
                "bandwidth_limit": resources.get("freeNetLimit", 0) + resources.get("NetLimit", 0),
                "bandwidth_used": resources.get("freeNetUsed", 0) + resources.get("NetUsed", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get resources for {address}: {e}")
            return {"energy": 0, "bandwidth": 0}

    # ============ Transaction Queries ============

    async def get_trc20_transactions(
        self,
        address: str,
        contract_address: str = None,
        only_confirmed: bool = True,
        only_to: bool = True,
        limit: int = 50,
        min_timestamp: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get TRC20 token transactions for an address.

        Args:
            address: TRON address
            contract_address: Filter by token contract (default: USDT)
            only_confirmed: Only return confirmed transactions
            only_to: Only return incoming transactions
            limit: Maximum number of transactions
            min_timestamp: Minimum timestamp (ms) to filter

        Returns:
            List of transaction records
        """
        client = await self._get_client()
        contract = contract_address or self.USDT_CONTRACT

        try:
            params = {
                "only_confirmed": str(only_confirmed).lower(),
                "only_to": str(only_to).lower(),
                "limit": limit,
                "contract_address": contract,
            }

            if min_timestamp:
                params["min_timestamp"] = min_timestamp

            response = await client.get(
                f"/v1/accounts/{address}/transactions/trc20",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            transactions = []
            for tx in data.get("data", []):
                amount_raw = int(tx.get("value", 0))
                amount = Decimal(amount_raw) / Decimal(10**self.USDT_DECIMALS)

                transactions.append(
                    {
                        "tx_hash": tx.get("transaction_id"),
                        "from_address": tx.get("from"),
                        "to_address": tx.get("to"),
                        "amount": amount,
                        "amount_raw": amount_raw,
                        "token_contract": tx.get("token_info", {}).get("address"),
                        "token_symbol": tx.get("token_info", {}).get("symbol"),
                        "block_timestamp": tx.get("block_timestamp"),
                        "confirmed": tx.get("confirmed", False),
                    }
                )

            return transactions

        except Exception as e:
            logger.error(f"Failed to get TRC20 transactions for {address}: {e}")
            return []

    async def get_transaction_info(self, tx_hash: str) -> dict[str, Any] | None:
        """Get detailed transaction information.

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction details including confirmation status
        """
        client = await self._get_client()

        try:
            response = await client.post(
                "/wallet/gettransactioninfobyid",
                json={"value": tx_hash},
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                return None

            return {
                "tx_hash": tx_hash,
                "block_number": data.get("blockNumber"),
                "block_timestamp": data.get("blockTimeStamp"),
                "fee": data.get("fee", 0),
                "energy_used": data.get("receipt", {}).get("energy_usage_total", 0),
                "net_used": data.get("receipt", {}).get("net_usage", 0),
                "result": data.get("receipt", {}).get("result"),
            }

        except Exception as e:
            logger.error(f"Failed to get transaction info for {tx_hash}: {e}")
            return None

    async def get_current_block(self) -> int:
        """Get current block number.

        Returns:
            Current block number
        """
        client = await self._get_client()

        try:
            response = await client.post("/wallet/getnowblock")
            response.raise_for_status()
            data = response.json()

            return data.get("block_header", {}).get("raw_data", {}).get("number", 0)

        except Exception as e:
            logger.error(f"Failed to get current block: {e}")
            return 0

    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get number of confirmations for a transaction.

        Args:
            tx_hash: Transaction hash

        Returns:
            Number of confirmations
        """
        tx_info = await self.get_transaction_info(tx_hash)
        if not tx_info or not tx_info.get("block_number"):
            return 0

        current_block = await self.get_current_block()
        if current_block == 0:
            return 0

        return max(0, current_block - tx_info["block_number"] + 1)

    # ============ Transaction Execution ============

    async def build_trc20_transfer(
        self,
        from_address: str,
        to_address: str,
        amount: Decimal,
        contract_address: str = None,
    ) -> dict[str, Any] | None:
        """Build a TRC20 transfer transaction (unsigned).

        Args:
            from_address: Sender address
            to_address: Recipient address
            amount: Amount to transfer
            contract_address: Token contract (default: USDT)

        Returns:
            Unsigned transaction or None on failure
        """
        client = await self._get_client()
        contract = contract_address or self.USDT_CONTRACT

        # Convert amount to raw (with decimals)
        amount_raw = int(amount * Decimal(10**self.USDT_DECIMALS))

        try:
            # Build transfer parameter
            # Function selector: transfer(address,uint256)
            # a9059cbb
            response = await client.post(
                "/wallet/triggersmartcontract",
                json={
                    "owner_address": from_address,
                    "contract_address": contract,
                    "function_selector": "transfer(address,uint256)",
                    "parameter": self._encode_transfer_params(to_address, amount_raw),
                    "fee_limit": 100000000,  # 100 TRX max fee
                    "call_value": 0,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("result", {}).get("result"):
                return data.get("transaction")
            else:
                logger.error(f"Failed to build TRC20 transfer: {data.get('result')}")
                return None

        except Exception as e:
            logger.error(f"Failed to build TRC20 transfer: {e}")
            return None

    def _encode_transfer_params(self, to_address: str, amount: int) -> str:
        """Encode transfer function parameters.

        Args:
            to_address: Recipient address (base58)
            amount: Amount in raw units

        Returns:
            Hex-encoded parameters
        """
        # Convert base58 address to hex (remove T prefix and convert)
        # This is a simplified version - in production use tronpy library
        try:
            import base58

            addr_bytes = base58.b58decode_check(to_address)
            addr_hex = addr_bytes.hex()[2:]  # Remove 41 prefix

            # Pad address to 32 bytes
            addr_padded = addr_hex.zfill(64)

            # Pad amount to 32 bytes
            amount_hex = hex(amount)[2:].zfill(64)

            return addr_padded + amount_hex

        except Exception as e:
            logger.error(f"Failed to encode transfer params: {e}")
            return ""

    async def sign_and_broadcast(
        self,
        transaction: dict[str, Any],
        private_key: str,
    ) -> str | None:
        """Sign and broadcast a transaction.

        Args:
            transaction: Unsigned transaction
            private_key: Private key (hex)

        Returns:
            Transaction hash or None on failure

        Note:
            This is a placeholder. In production, use tronpy library
            for proper signing to avoid sending private keys to API.
        """
        # WARNING: This is insecure for production!
        # In production, use local signing with tronpy:
        #
        # from tronpy.keys import PrivateKey
        # priv = PrivateKey(bytes.fromhex(private_key))
        # signed_txn = transaction.sign(priv)
        # result = await client.broadcast(signed_txn)

        logger.warning("sign_and_broadcast is not implemented for security reasons")
        logger.warning("Use tronpy library for local signing in production")

        # Placeholder - implement with tronpy
        return None

    # ============ Monitoring Utilities ============

    async def watch_address_deposits(
        self,
        addresses: list[str],
        callback,
        poll_interval: int = 10,
        min_timestamp: int | None = None,
    ):
        """Watch multiple addresses for incoming deposits.

        Args:
            addresses: List of addresses to watch
            callback: Async callback function(address, tx) for each deposit
            poll_interval: Polling interval in seconds
            min_timestamp: Start watching from this timestamp (ms)

        Note:
            This is a simple polling implementation.
            For production, consider using TronGrid's subscription API
            or webhook services.
        """
        import time

        last_check = min_timestamp or int(time.time() * 1000)
        seen_txs: set[str] = set()

        while True:
            for address in addresses:
                try:
                    transactions = await self.get_trc20_transactions(
                        address=address,
                        only_confirmed=True,
                        only_to=True,
                        min_timestamp=last_check,
                    )

                    for tx in transactions:
                        tx_hash = tx["tx_hash"]
                        if tx_hash and tx_hash not in seen_txs:
                            seen_txs.add(tx_hash)
                            await callback(address, tx)

                except Exception as e:
                    logger.error(f"Error watching address {address}: {e}")

            last_check = int(time.time() * 1000)
            await asyncio.sleep(poll_interval)


# Singleton instance
_tron_service: TronService | None = None


def get_tron_service() -> TronService:
    """Get TRON service singleton."""
    global _tron_service
    if _tron_service is None:
        _tron_service = TronService()
    return _tron_service
