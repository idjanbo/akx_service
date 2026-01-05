"""Wallet Service - Business logic for wallet operations."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.security import get_cipher
from src.models.chain import Chain
from src.models.token import Token
from src.models.user import User, UserRole
from src.models.wallet import Wallet, WalletType
from src.utils.crypto import generate_wallet_for_chain, validate_address_for_chain
from src.utils.helpers import get_token_name
from src.utils.pagination import PaginatedResult, PaginationParams, paginate_query


class WalletService:
    """Service for wallet-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Wallet CRUD Operations ============

    async def list_wallets(
        self,
        user: User,
        params: PaginationParams,
        chain_id: int | None = None,
        token_id: int | None = None,
        source: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """List wallets with filters and pagination.

        Args:
            user: Current user (for role-based filtering)
            params: Pagination parameters
            chain_id: Filter by chain ID
            token_id: Filter by token ID
            source: Filter by source (SYSTEM_GENERATED/MANUAL_IMPORT)
            is_active: Filter by active status

        Returns:
            Paginated wallet list with related data
        """
        query = select(Wallet)

        # Role-based filtering
        if user.role == UserRole.MERCHANT:
            query = query.where(Wallet.user_id == user.id)

        # Apply filters
        if chain_id:
            query = query.where(Wallet.chain_id == chain_id)
        if token_id:
            query = query.where(Wallet.token_id == token_id)
        if source:
            if source == "SYSTEM_GENERATED":
                query = query.where(Wallet.wallet_type == WalletType.DEPOSIT)
            elif source == "MANUAL_IMPORT":
                query = query.where(Wallet.wallet_type == WalletType.MERCHANT)
        if is_active is not None:
            query = query.where(Wallet.is_active == is_active)

        query = query.order_by(Wallet.created_at.desc())

        # Paginate
        wallets, total = await paginate_query(self.db, query, params)

        # Get related data
        chain_names = await self._get_chain_names([w.chain_id for w in wallets])
        token_symbols = await self._get_token_symbols([w.token_id for w in wallets if w.token_id])
        user_names = await self._get_user_names([w.user_id for w in wallets if w.user_id])

        # Build response items
        items = [self._wallet_to_dict(w, chain_names, token_symbols, user_names) for w in wallets]

        return PaginatedResult(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_wallet(self, wallet_id: int, user: User) -> dict[str, Any] | None:
        """Get a single wallet by ID.

        Args:
            wallet_id: Wallet ID
            user: Current user (for access control)

        Returns:
            Wallet dict or None if not found/not accessible
        """
        wallet = await self.db.get(Wallet, wallet_id)
        if not wallet:
            return None

        # Check ownership for merchants
        if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
            return None

        chain = await self.db.get(Chain, wallet.chain_id)
        chain_name = chain.name if chain else "Unknown"

        merchant_name = None
        if wallet.user_id:
            merchant = await self.db.get(User, wallet.user_id)
            merchant_name = merchant.email if merchant else None

        return {
            "id": wallet.id,
            "chain_id": wallet.chain_id,
            "chain_name": chain_name,
            "token_id": wallet.token_id,
            "token_symbol": None,  # Can be fetched if needed
            "address": wallet.address,
            "source": "SYSTEM_GENERATED"
            if wallet.wallet_type == WalletType.DEPOSIT
            else "MANUAL_IMPORT",
            "balance": wallet.balance or None,
            "merchant_id": wallet.user_id,
            "merchant_name": merchant_name,
            "remark": wallet.label,
            "is_active": wallet.is_active,
            "created_at": wallet.created_at.isoformat() if wallet.created_at else "",
        }

    async def generate_wallets(
        self,
        user: User,
        chain_id: int,
        count: int,
        token_id: int | None = None,
    ) -> tuple[list[Wallet], Chain]:
        """Generate new wallet addresses.

        Args:
            user: Current user (owner of wallets)
            chain_id: Chain to generate wallets for
            count: Number of wallets to generate
            token_id: Token ID (optional, defaults to USDT)

        Returns:
            Tuple of (created wallets, chain)

        Raises:
            ValueError: If chain not found or disabled
        """
        # Verify chain
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            raise ValueError(f"Chain with id {chain_id} not found")
        if not chain.is_enabled:
            raise ValueError(f"Chain {chain.name} is not enabled")

        # Verify token if provided, or default to USDT
        resolved_token_id = await self._resolve_token_id(token_id)

        # Generate wallets
        cipher = get_cipher()
        created_wallets: list[Wallet] = []

        for _ in range(count):
            address, private_key = generate_wallet_for_chain(chain.code)
            encrypted_pk = cipher.encrypt(private_key)

            wallet = Wallet(
                user_id=user.id,
                chain_id=chain_id,
                token_id=resolved_token_id,
                address=address,
                encrypted_private_key=encrypted_pk,
                wallet_type=WalletType.DEPOSIT,
                is_active=True,
            )
            self.db.add(wallet)
            created_wallets.append(wallet)

        await self.db.commit()
        for w in created_wallets:
            await self.db.refresh(w)

        return created_wallets, chain

    async def import_wallet(
        self,
        user: User,
        chain_id: int,
        address: str,
        private_key: str,
        token_id: int | None = None,
        label: str | None = None,
    ) -> tuple[Wallet, Chain]:
        """Import an existing wallet.

        Args:
            user: Current user
            chain_id: Chain ID
            address: Wallet address
            private_key: Private key (will be encrypted)
            token_id: Token ID (optional)
            label: Optional label

        Returns:
            Tuple of (wallet, chain)

        Raises:
            ValueError: If validation fails
        """
        # Verify chain
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            raise ValueError(f"Chain with id {chain_id} not found")

        # Resolve token
        resolved_token_id = await self._resolve_token_id(token_id)

        # Check if address already exists
        existing = await self.db.execute(select(Wallet).where(Wallet.address == address))
        if existing.scalar_one_or_none():
            raise ValueError("Wallet address already exists")

        # Validate address format
        if not validate_address_for_chain(chain.code, address):
            raise ValueError(f"Invalid address format for {chain.name}")

        # Encrypt and create
        cipher = get_cipher()
        encrypted_pk = cipher.encrypt(private_key)

        wallet = Wallet(
            user_id=user.id,
            chain_id=chain_id,
            token_id=resolved_token_id,
            address=address,
            encrypted_private_key=encrypted_pk,
            wallet_type=WalletType.MERCHANT,
            is_active=True,
            label=label,
        )

        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)

        return wallet, chain

    async def update_wallet(
        self,
        wallet_id: int,
        user: User,
        label: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update wallet label or status.

        Args:
            wallet_id: Wallet ID
            user: Current user
            label: New label (optional)
            is_active: New active status (optional)

        Returns:
            Updated wallet dict or None
        """
        wallet = await self.db.get(Wallet, wallet_id)
        if not wallet:
            return None

        if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
            return None

        if label is not None:
            wallet.label = label
        if is_active is not None:
            wallet.is_active = is_active

        await self.db.commit()
        await self.db.refresh(wallet)

        return await self.get_wallet(wallet_id, user)

    async def delete_wallet(self, wallet_id: int, user: User) -> bool:
        """Delete a wallet.

        Args:
            wallet_id: Wallet ID
            user: Current user

        Returns:
            True if deleted, False otherwise

        Raises:
            ValueError: If wallet has non-zero balance
        """
        wallet = await self.db.get(Wallet, wallet_id)
        if not wallet:
            return False

        if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
            return False

        if wallet.balance and wallet.balance != "0":
            raise ValueError("Cannot delete wallet with non-zero balance")

        await self.db.delete(wallet)
        await self.db.commit()
        return True

    # ============ Asset Summary ============

    async def get_asset_summary(self, user: User) -> dict[str, Any]:
        """Get asset summary for the user.

        Args:
            user: Current user

        Returns:
            Asset summary with balance, trends, and grouped addresses
        """
        # Get all active wallets
        query = select(Wallet).where(Wallet.is_active == True)  # noqa: E712
        if user.role == UserRole.MERCHANT:
            query = query.where(Wallet.user_id == user.id)

        result = await self.db.execute(query)
        wallets = result.scalars().all()

        # Get lookup maps
        chains_result = await self.db.execute(select(Chain))
        chains_map = {c.id: c for c in chains_result.scalars()}

        tokens_result = await self.db.execute(select(Token))
        tokens_map = {t.id: t for t in tokens_result.scalars()}

        # Calculate balances
        total_balance = 0.0
        asset_balances: dict[str, float] = {}
        chain_wallets: dict[str, dict[int, list[Wallet]]] = {}

        for wallet in wallets:
            balance = float(wallet.balance) if wallet.balance else 0.0
            chain = chains_map.get(wallet.chain_id)
            if not chain:
                continue

            # Get token symbol
            if wallet.token_id and wallet.token_id in tokens_map:
                symbol = tokens_map[wallet.token_id].symbol
            else:
                symbol = "USDT"

            total_balance += balance
            asset_balances[symbol] = asset_balances.get(symbol, 0.0) + balance

            if symbol not in chain_wallets:
                chain_wallets[symbol] = {}
            if wallet.chain_id not in chain_wallets[symbol]:
                chain_wallets[symbol][wallet.chain_id] = []
            chain_wallets[symbol][wallet.chain_id].append(wallet)

        # Build response
        assets = [
            {
                "symbol": symbol,
                "name": get_token_name(symbol),
                "amount": f"{amount:,.2f}",
                "fiat_symbol": "¥",
                "fiat_value": f"{amount:,.2f}",
            }
            for symbol, amount in asset_balances.items()
        ]

        asset_chains: dict[str, list[dict[str, Any]]] = {}
        for symbol, chain_groups in chain_wallets.items():
            asset_chains[symbol] = []
            for chain_id, wallet_list in chain_groups.items():
                chain = chains_map.get(chain_id)
                if not chain:
                    continue

                addresses = [
                    {
                        "id": w.id,
                        "address": w.address,
                        "balance": f"{float(w.balance) if w.balance else 0:.2f} {symbol}",
                        "is_default": i == 0,
                        "label": w.label,
                    }
                    for i, w in enumerate(wallet_list)
                ]

                asset_chains[symbol].append(
                    {
                        "chain": chain.name,
                        "chain_id": chain_id,
                        "addresses": addresses,
                    }
                )

        # Generate trend data
        import random

        base_value = total_balance if total_balance > 0 else 1000
        trend_data = [round(base_value * (0.95 + random.random() * 0.1), 2) for _ in range(28)]
        trend_data[-1] = round(total_balance, 2)

        yesterday_value = trend_data[-5] if len(trend_data) > 5 else total_balance
        today_change = total_balance - yesterday_value
        today_change_percent = (today_change / yesterday_value * 100) if yesterday_value > 0 else 0

        return {
            "balance": {
                "amount": f"{total_balance:,.2f}",
                "base_asset": "USDT",
                "fiat_symbol": "¥",
                "fiat_currency": "CNY",
                "fiat_value": f"{total_balance:,.2f}",
                "today_change": f"{abs(today_change):.2f}",
                "today_change_percent": f"{today_change_percent:.2f}",
            },
            "trend_data": trend_data,
            "assets": assets,
            "asset_chains": asset_chains,
        }

    # ============ Helper Methods ============

    async def _resolve_token_id(self, token_id: int | None) -> int | None:
        """Resolve token ID, defaulting to USDT if not specified."""
        if token_id:
            token = await self.db.get(Token, token_id)
            if not token:
                raise ValueError(f"Token with id {token_id} not found")
            if not token.is_enabled:
                raise ValueError(f"Token {token.symbol} is not enabled")
            return token_id

        # Default to USDT
        result = await self.db.execute(select(Token).where(Token.code == "usdt"))
        usdt_token = result.scalar_one_or_none()
        return usdt_token.id if usdt_token else None

    async def _get_chain_names(self, chain_ids: list[int]) -> dict[int, str]:
        """Get chain names by IDs."""
        if not chain_ids:
            return {}
        unique_ids = list(set(chain_ids))
        result = await self.db.execute(select(Chain).where(Chain.id.in_(unique_ids)))
        return {c.id: c.name for c in result.scalars()}

    async def _get_token_symbols(self, token_ids: list[int]) -> dict[int, str]:
        """Get token symbols by IDs."""
        if not token_ids:
            return {}
        unique_ids = list(set(token_ids))
        result = await self.db.execute(select(Token).where(Token.id.in_(unique_ids)))
        return {t.id: t.symbol for t in result.scalars()}

    async def _get_user_names(self, user_ids: list[int]) -> dict[int, str]:
        """Get user emails by IDs."""
        if not user_ids:
            return {}
        unique_ids = list(set(user_ids))
        result = await self.db.execute(select(User).where(User.id.in_(unique_ids)))
        return {u.id: u.email for u in result.scalars()}

    def _wallet_to_dict(
        self,
        wallet: Wallet,
        chain_names: dict[int, str],
        token_symbols: dict[int, str],
        user_names: dict[int, str],
    ) -> dict[str, Any]:
        """Convert wallet to response dict."""
        return {
            "id": wallet.id,
            "chain_id": wallet.chain_id,
            "chain_name": chain_names.get(wallet.chain_id, "Unknown"),
            "token_id": wallet.token_id,
            "token_symbol": token_symbols.get(wallet.token_id) if wallet.token_id else None,
            "address": wallet.address,
            "source": "SYSTEM_GENERATED"
            if wallet.wallet_type == WalletType.DEPOSIT
            else "MANUAL_IMPORT",
            "balance": wallet.balance or None,
            "merchant_id": wallet.user_id,
            "merchant_name": user_names.get(wallet.user_id) if wallet.user_id else None,
            "remark": wallet.label,
            "is_active": wallet.is_active,
            "created_at": wallet.created_at.isoformat() if wallet.created_at else "",
        }
