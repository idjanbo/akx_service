"""AKX Crypto Payment Gateway - Wallet service."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.chains import get_chain
from src.core.security import decrypt_private_key, encrypt_private_key
from src.models.wallet import Chain, Wallet, WalletType


class WalletService:
    """Service for wallet generation and management.

    Handles wallet creation, private key encryption/decryption,
    and wallet queries.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_wallet(
        self,
        user_id: int,
        chain: Chain,
        wallet_type: WalletType = WalletType.DEPOSIT,
        label: str | None = None,
    ) -> Wallet:
        """Generate a new wallet for the user.

        Args:
            user_id: Owner merchant ID
            chain: Blockchain network (TRON, ETH, SOL)
            wallet_type: Purpose of wallet
            label: Optional human-readable name

        Returns:
            Created wallet (with encrypted private key)
        """
        # Generate wallet using chain implementation
        chain_impl = get_chain(chain)
        wallet_info = chain_impl.generate_wallet()

        # Encrypt private key before storage
        encrypted_key = encrypt_private_key(wallet_info.private_key)

        # Create wallet record
        wallet = Wallet(
            user_id=user_id,
            chain=chain,
            address=wallet_info.address,
            encrypted_private_key=encrypted_key,
            wallet_type=wallet_type,
            label=label,
            is_active=True,
        )

        self._db.add(wallet)
        await self._db.commit()
        await self._db.refresh(wallet)

        return wallet

    async def get_wallet_by_address(
        self,
        address: str,
        chain: Chain | None = None,
    ) -> Wallet | None:
        """Find wallet by blockchain address.

        Args:
            address: Blockchain address
            chain: Optional chain filter

        Returns:
            Wallet if found, None otherwise
        """
        query = select(Wallet).where(Wallet.address == address)
        if chain:
            query = query.where(Wallet.chain == chain)

        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_wallets(
        self,
        user_id: int,
        chain: Chain | None = None,
        wallet_type: WalletType | None = None,
        active_only: bool = True,
    ) -> list[Wallet]:
        """Get all wallets for a user.

        Args:
            user_id: Merchant user ID
            chain: Optional chain filter
            wallet_type: Optional type filter
            active_only: Whether to return only active wallets

        Returns:
            List of wallets
        """
        query = select(Wallet).where(Wallet.user_id == user_id)

        if chain:
            query = query.where(Wallet.chain == chain)
        if wallet_type:
            query = query.where(Wallet.wallet_type == wallet_type)
        if active_only:
            query = query.where(Wallet.is_active == True)  # noqa: E712

        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def get_deposit_address(
        self,
        user_id: int,
        chain: Chain,
    ) -> Wallet:
        """Get or create a deposit address for the user.

        If user already has an active deposit wallet for the chain,
        returns that. Otherwise creates a new one.

        Args:
            user_id: Merchant user ID
            chain: Blockchain network

        Returns:
            Deposit wallet
        """
        # Check for existing deposit wallet
        wallets = await self.get_user_wallets(
            user_id=user_id,
            chain=chain,
            wallet_type=WalletType.DEPOSIT,
        )

        if wallets:
            return wallets[0]

        # Create new deposit wallet
        return await self.create_wallet(
            user_id=user_id,
            chain=chain,
            wallet_type=WalletType.DEPOSIT,
            label=f"{chain.value.upper()} Deposit",
        )

    def get_private_key(self, wallet: Wallet) -> str:
        """Decrypt and return wallet private key.

        WARNING: Handle with care! Clear from memory after use.

        Args:
            wallet: Wallet with encrypted private key

        Returns:
            Decrypted private key
        """
        return decrypt_private_key(wallet.encrypted_private_key)

    async def deactivate_wallet(self, wallet_id: int) -> bool:
        """Deactivate a wallet (soft delete).

        Args:
            wallet_id: Wallet ID to deactivate

        Returns:
            True if successful
        """
        result = await self._db.execute(select(Wallet).where(Wallet.id == wallet_id))
        wallet = result.scalar_one_or_none()

        if wallet:
            wallet.is_active = False
            await self._db.commit()
            return True

        return False
