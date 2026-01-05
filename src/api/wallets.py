"""AKX - Wallets API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from src.api.auth import get_current_user
from src.core.security import get_cipher
from src.db import get_db
from src.models.chain import Chain
from src.models.token import Token
from src.models.user import User, UserRole
from src.models.wallet import Wallet, WalletType

router = APIRouter()


class WalletResponse(BaseModel):
    """Wallet response model."""

    id: int
    chain_id: int
    chain_name: str
    token_id: int | None
    token_symbol: str | None
    address: str
    source: str  # SYSTEM_GENERATED or MANUAL_IMPORT
    balance: str | None
    merchant_id: int | None
    merchant_name: str | None
    remark: str | None
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class PaginatedWalletsResponse(BaseModel):
    """Paginated wallets response."""

    items: list[WalletResponse]
    total: int
    page: int
    page_size: int


class GenerateWalletsRequest(BaseModel):
    """Request model for generating wallets."""

    chain_id: int = PydanticField(..., description="Chain ID to generate wallets for")
    token_id: int | None = PydanticField(
        None, description="Token ID (optional, defaults to primary stablecoin)"
    )
    count: int = PydanticField(1, ge=1, le=100, description="Number of addresses to generate")


class GenerateWalletsResponse(BaseModel):
    """Response model for generated wallets."""

    wallets: list[WalletResponse]
    count: int


class ImportWalletRequest(BaseModel):
    """Request model for importing a wallet."""

    chain_id: int = PydanticField(..., description="Chain ID")
    token_id: int | None = PydanticField(
        None, description="Token ID (optional, defaults to primary stablecoin)"
    )
    address: str = PydanticField(..., min_length=10, max_length=255, description="Wallet address")
    private_key: str = PydanticField(..., min_length=10, description="Private key")
    label: str | None = PydanticField(None, max_length=255, description="Optional label")


class UpdateWalletRequest(BaseModel):
    """Request model for updating a wallet."""

    label: str | None = PydanticField(None, max_length=255, description="Optional label")
    is_active: bool | None = PydanticField(None, description="Whether wallet is active")


# ============ Asset Summary Models ============


class AssetBalanceResponse(BaseModel):
    """Total asset balance overview."""

    amount: str
    base_asset: str
    fiat_symbol: str
    fiat_currency: str
    fiat_value: str
    today_change: str
    today_change_percent: str


class AssetResponse(BaseModel):
    """Single asset info."""

    symbol: str
    name: str
    amount: str
    fiat_symbol: str
    fiat_value: str


class AddressBalanceResponse(BaseModel):
    """Address balance info."""

    id: int
    address: str
    balance: str
    is_default: bool
    label: str | None


class ChainAddressGroupResponse(BaseModel):
    """Chain address group."""

    chain: str
    chain_id: int
    addresses: list[AddressBalanceResponse]


class AssetSummaryResponse(BaseModel):
    """Asset summary response."""

    balance: AssetBalanceResponse
    trend_data: list[float]
    assets: list[AssetResponse]
    asset_chains: dict[str, list[ChainAddressGroupResponse]]


@router.get("/assets/summary", response_model=AssetSummaryResponse)
async def get_asset_summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssetSummaryResponse:
    """Get asset summary for the current user.

    Returns total balance, trend data, asset list, and addresses grouped by chain.
    """
    # Get all active wallets for the user
    query = select(Wallet).where(Wallet.is_active == True)  # noqa: E712

    if user.role == UserRole.MERCHANT:
        query = query.where(Wallet.user_id == user.id)

    result = await db.execute(query)
    wallets = result.scalars().all()

    # Get all chains for lookup
    chains_result = await db.execute(select(Chain))
    chains_map: dict[int, Chain] = {c.id: c for c in chains_result.scalars()}  # type: ignore

    # Get all tokens for lookup
    tokens_result = await db.execute(select(Token))
    tokens_map: dict[int, Token] = {t.id: t for t in tokens_result.scalars()}  # type: ignore

    # Calculate total balance and group by token/chain
    total_balance = 0.0
    asset_balances: dict[str, float] = {}  # symbol -> total amount
    chain_wallets: dict[str, dict[int, list[Wallet]]] = {}  # symbol -> chain_id -> wallets

    for wallet in wallets:
        balance = float(wallet.balance) if wallet.balance else 0.0
        chain = chains_map.get(wallet.chain_id)
        if not chain:
            continue

        # Get token symbol from token_id, or use chain's native token as default
        if wallet.token_id and wallet.token_id in tokens_map:
            token = tokens_map[wallet.token_id]
            symbol = token.symbol
        else:
            # Default: use USDT as the primary stablecoin
            symbol = "USDT"

        total_balance += balance
        asset_balances[symbol] = asset_balances.get(symbol, 0.0) + balance

        if symbol not in chain_wallets:
            chain_wallets[symbol] = {}
        if wallet.chain_id not in chain_wallets[symbol]:
            chain_wallets[symbol][wallet.chain_id] = []
        chain_wallets[symbol][wallet.chain_id].append(wallet)

    # Build assets list
    assets: list[AssetResponse] = []
    for symbol, amount in asset_balances.items():
        assets.append(
            AssetResponse(
                symbol=symbol,
                name=_get_token_name(symbol),
                amount=f"{amount:,.2f}",
                fiat_symbol="¥",
                fiat_value=f"{amount:,.2f}",  # 1:1 for USDT
            )
        )

    # Build asset_chains
    asset_chains: dict[str, list[ChainAddressGroupResponse]] = {}
    for symbol, chain_groups in chain_wallets.items():
        asset_chains[symbol] = []
        for chain_id, chain_wallet_list in chain_groups.items():
            chain = chains_map.get(chain_id)
            if not chain:
                continue

            addresses = [
                AddressBalanceResponse(
                    id=w.id,  # type: ignore
                    address=w.address,
                    balance=f"{float(w.balance) if w.balance else 0:.2f} {symbol}",
                    is_default=False,
                    label=w.label,
                )
                for w in chain_wallet_list
            ]
            # Mark first address as default
            if addresses:
                addresses[0].is_default = True

            asset_chains[symbol].append(
                ChainAddressGroupResponse(
                    chain=chain.name,
                    chain_id=chain_id,
                    addresses=addresses,
                )
            )

    # Generate mock trend data (7 days, 4 points per day = 28 points)
    # In production, this would come from historical balance snapshots
    import random

    base_value = total_balance if total_balance > 0 else 1000
    trend_data = [round(base_value * (0.95 + random.random() * 0.1), 2) for _ in range(28)]
    trend_data[-1] = round(total_balance, 2)  # Last point is current balance

    # Calculate today's change (mock)
    yesterday_value = trend_data[-5] if len(trend_data) > 5 else total_balance
    today_change = total_balance - yesterday_value
    today_change_percent = (today_change / yesterday_value * 100) if yesterday_value > 0 else 0

    return AssetSummaryResponse(
        balance=AssetBalanceResponse(
            amount=f"{total_balance:,.2f}",
            base_asset="USDT",
            fiat_symbol="¥",
            fiat_currency="CNY",
            fiat_value=f"{total_balance:,.2f}",
            today_change=f"{abs(today_change):.2f}",
            today_change_percent=f"{today_change_percent:.2f}",
        ),
        trend_data=trend_data,
        assets=assets,
        asset_chains=asset_chains,
    )


def _get_token_name(symbol: str) -> str:
    """Get token full name from symbol."""
    names = {
        "USDT": "Tether",
        "USDC": "USD Coin",
        "ETH": "Ethereum",
        "BTC": "Bitcoin",
        "TRX": "TRON",
        "SOL": "Solana",
    }
    return names.get(symbol, symbol)


@router.get("", response_model=PaginatedWalletsResponse)
async def list_wallets(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    chain_id: int | None = None,
    token_id: int | None = None,
    source: str | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedWalletsResponse:
    """List wallets with filters.

    Merchants can only see their own wallets.
    Admins can see all wallets.
    """
    query = select(Wallet)

    # Filter by user role
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

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(Wallet.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    wallets = result.scalars().all()

    # Get chain names
    chain_ids = list({w.chain_id for w in wallets})
    chain_names: dict[int, str] = {}
    if chain_ids:
        chains_result = await db.execute(select(Chain).where(Chain.id.in_(chain_ids)))
        for c in chains_result.scalars():
            chain_names[c.id] = c.name  # type: ignore

    # Get token symbols
    token_ids = list({w.token_id for w in wallets if w.token_id})
    token_symbols: dict[int, str] = {}
    if token_ids:
        tokens_result = await db.execute(select(Token).where(Token.id.in_(token_ids)))
        for t in tokens_result.scalars():
            token_symbols[t.id] = t.symbol  # type: ignore

    # Get user names (merchants)
    user_ids = list({w.user_id for w in wallets if w.user_id})
    user_names: dict[int, str] = {}
    if user_ids:
        from src.models.user import User as UserModel

        users_result = await db.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
        for u in users_result.scalars():
            user_names[u.id] = u.email  # type: ignore

    return PaginatedWalletsResponse(
        items=[
            WalletResponse(
                id=w.id,  # type: ignore
                chain_id=w.chain_id,
                chain_name=chain_names.get(w.chain_id, "Unknown"),
                token_id=w.token_id,
                token_symbol=token_symbols.get(w.token_id) if w.token_id else None,
                address=w.address,
                source=(
                    "SYSTEM_GENERATED" if w.wallet_type == WalletType.DEPOSIT else "MANUAL_IMPORT"
                ),
                balance=w.balance or None,
                merchant_id=w.user_id,
                merchant_name=user_names.get(w.user_id) if w.user_id else None,
                remark=w.label,
                is_active=w.is_active,
                created_at=w.created_at.isoformat() if w.created_at else "",
            )
            for w in wallets
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/generate", response_model=GenerateWalletsResponse)
async def generate_wallets(
    request: GenerateWalletsRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerateWalletsResponse:
    """Generate new wallet addresses for a chain.

    This creates system-generated deposit wallets.
    """
    # Verify chain exists and is enabled
    chain = await db.get(Chain, request.chain_id)
    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chain with id {request.chain_id} not found",
        )
    if not chain.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chain {chain.name} is not enabled",
        )

    # Verify token exists if provided
    token_id = request.token_id
    if token_id:
        token = await db.get(Token, token_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token with id {token_id} not found",
            )
        if not token.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token {token.symbol} is not enabled",
            )
    else:
        # Default to USDT if not specified
        result = await db.execute(select(Token).where(Token.code == "usdt"))
        usdt_token = result.scalar_one_or_none()
        if usdt_token:
            token_id = usdt_token.id

    # Generate wallets based on chain
    cipher = get_cipher()
    created_wallets: list[Wallet] = []

    for _ in range(request.count):
        # Generate address and private key based on chain
        address, private_key = _generate_wallet_for_chain(chain.code)

        # Encrypt private key
        encrypted_pk = cipher.encrypt(private_key)

        wallet = Wallet(
            user_id=user.id,  # Always bind to current user
            chain_id=request.chain_id,
            token_id=token_id,  # Now properly set token_id
            address=address,
            encrypted_private_key=encrypted_pk,
            wallet_type=WalletType.DEPOSIT,
            is_active=True,
        )
        db.add(wallet)
        created_wallets.append(wallet)

    await db.commit()

    # Refresh to get IDs
    for w in created_wallets:
        await db.refresh(w)

    return GenerateWalletsResponse(
        wallets=[
            WalletResponse(
                id=w.id,  # type: ignore
                chain_id=w.chain_id,
                chain_name=chain.name,
                address=w.address,
                source="SYSTEM_GENERATED",
                balance="0",
                merchant_id=w.user_id,
                merchant_name=user.email if w.user_id else None,
                remark=w.label,
                is_active=w.is_active,
                created_at=w.created_at.isoformat() if w.created_at else "",
            )
            for w in created_wallets
        ],
        count=len(created_wallets),
    )


@router.post("/import", response_model=WalletResponse)
async def import_wallet(
    request: ImportWalletRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WalletResponse:
    """Import an existing wallet with private key.

    Security Note: Private key is encrypted before storage.
    """
    # Verify chain exists
    chain = await db.get(Chain, request.chain_id)
    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chain with id {request.chain_id} not found",
        )

    # Verify token exists if provided
    token_id = request.token_id
    if token_id:
        token = await db.get(Token, token_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token with id {token_id} not found",
            )
    else:
        # Default to USDT if not specified
        result = await db.execute(select(Token).where(Token.code == "usdt"))
        usdt_token = result.scalar_one_or_none()
        if usdt_token:
            token_id = usdt_token.id

    # Check if address already exists
    existing = await db.execute(select(Wallet).where(Wallet.address == request.address))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet address already exists",
        )

    # Validate address format based on chain
    if not _validate_address_for_chain(chain.code, request.address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid address format for {chain.name}",
        )

    # Encrypt private key
    cipher = get_cipher()
    encrypted_pk = cipher.encrypt(request.private_key)

    wallet = Wallet(
        user_id=user.id,
        chain_id=request.chain_id,
        token_id=token_id,  # Now properly set token_id
        address=request.address,
        encrypted_private_key=encrypted_pk,
        wallet_type=WalletType.MERCHANT,  # Manual imports are merchant wallets
        is_active=True,
        label=request.label,
    )

    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    return WalletResponse(
        id=wallet.id,  # type: ignore
        chain_id=wallet.chain_id,
        chain_name=chain.name,
        address=wallet.address,
        source="MANUAL_IMPORT",
        balance="0",
        merchant_id=wallet.user_id,
        merchant_name=user.email,
        remark=wallet.label,
        is_active=wallet.is_active,
        created_at=wallet.created_at.isoformat() if wallet.created_at else "",
    )


def _generate_wallet_for_chain(chain_code: str) -> tuple[str, str]:
    """Generate a wallet address and private key for the given chain.

    Args:
        chain_code: Chain code (e.g., 'tron', 'ethereum', 'solana')

    Returns:
        Tuple of (address, private_key)

    Note: This is a placeholder implementation. Real implementations should use:
        - tronpy for TRON
        - web3.py for Ethereum
        - solana-py for Solana
    """
    import secrets

    # Generate a random 32-byte private key (placeholder)
    private_key = secrets.token_hex(32)

    if chain_code.lower() == "tron":
        # TRON addresses start with 'T'
        # Real implementation: use tronpy.Tron().generate_address()
        address = "T" + secrets.token_hex(16).upper()[:33]
    elif chain_code.lower() == "ethereum":
        # Ethereum addresses are 40 hex chars prefixed with 0x
        # Real implementation: use web3.eth.account.create()
        address = "0x" + secrets.token_hex(20)
    elif chain_code.lower() == "solana":
        # Solana addresses are base58-encoded 32-byte public keys
        # Real implementation: use solana.keypair.Keypair.generate()
        import base64

        address = base64.b64encode(secrets.token_bytes(32)).decode()[:44]
    else:
        # Generic fallback
        address = secrets.token_hex(20)

    return address, private_key


def _validate_address_for_chain(chain_code: str, address: str) -> bool:
    """Validate wallet address format for the given chain.

    Args:
        chain_code: Chain code (e.g., 'tron', 'ethereum', 'solana')
        address: Wallet address to validate

    Returns:
        True if valid, False otherwise

    Note: This is a basic implementation. Real validation should use chain-specific libraries.
    """
    chain_code = chain_code.lower()

    if chain_code == "tron":
        # TRON addresses start with 'T' and are 34 characters
        return address.startswith("T") and len(address) == 34
    elif chain_code == "ethereum":
        # Ethereum addresses are 42 characters (0x + 40 hex)
        return address.startswith("0x") and len(address) == 42
    elif chain_code == "solana":
        # Solana addresses are 32-44 characters base58
        return 32 <= len(address) <= 44

    # Accept any address for unknown chains
    return True


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WalletResponse:
    """Get a single wallet by ID."""
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    # Check ownership for merchants
    if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this wallet",
        )

    # Get chain name
    chain = await db.get(Chain, wallet.chain_id)
    chain_name = chain.name if chain else "Unknown"

    # Get merchant name
    merchant_name = None
    if wallet.user_id:
        merchant = await db.get(User, wallet.user_id)
        merchant_name = merchant.email if merchant else None

    return WalletResponse(
        id=wallet.id,  # type: ignore
        chain_id=wallet.chain_id,
        chain_name=chain_name,
        address=wallet.address,
        source="SYSTEM_GENERATED" if wallet.wallet_type == WalletType.DEPOSIT else "MANUAL_IMPORT",
        balance=wallet.balance or None,
        merchant_id=wallet.user_id,
        merchant_name=merchant_name,
        remark=wallet.label,
        is_active=wallet.is_active,
        created_at=wallet.created_at.isoformat() if wallet.created_at else "",
    )


@router.patch("/{wallet_id}", response_model=WalletResponse)
async def update_wallet(
    wallet_id: int,
    request: UpdateWalletRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WalletResponse:
    """Update a wallet's label or status."""
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    # Check ownership for merchants
    if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this wallet",
        )

    # Update fields if provided
    if request.label is not None:
        wallet.label = request.label
    if request.is_active is not None:
        wallet.is_active = request.is_active

    await db.commit()
    await db.refresh(wallet)

    # Get chain name
    chain = await db.get(Chain, wallet.chain_id)
    chain_name = chain.name if chain else "Unknown"

    # Get merchant name
    merchant_name = None
    if wallet.user_id:
        merchant = await db.get(User, wallet.user_id)
        merchant_name = merchant.email if merchant else None

    return WalletResponse(
        id=wallet.id,  # type: ignore
        chain_id=wallet.chain_id,
        chain_name=chain_name,
        address=wallet.address,
        source="SYSTEM_GENERATED" if wallet.wallet_type == WalletType.DEPOSIT else "MANUAL_IMPORT",
        balance=wallet.balance or None,
        merchant_id=wallet.user_id,
        merchant_name=merchant_name,
        remark=wallet.label,
        is_active=wallet.is_active,
        created_at=wallet.created_at.isoformat() if wallet.created_at else "",
    )


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a wallet.

    Note: Only wallets with zero balance can be deleted for safety.
    """
    wallet = await db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    # Check ownership for merchants
    if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this wallet",
        )

    # Safety check: only allow deletion of wallets with zero balance
    if wallet.balance and wallet.balance != "0":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete wallet with non-zero balance",
        )

    await db.delete(wallet)
    await db.commit()
