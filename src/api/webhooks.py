"""Webhook endpoints for receiving blockchain notifications.

Receives transaction notifications from third-party services:
- TronGrid Event API (TRON)
- Alchemy Webhooks (Ethereum, Polygon, etc.)
- Helius Webhooks (Solana)
- QuickNode Streams (Multi-chain)
- Moralis Streams (Multi-chain)

Each provider has different payload formats and signature verification methods.
Provider credentials are stored in the database and retrieved dynamically.
"""

import hashlib
import hmac
import logging
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import and_, select

from src.db.engine import get_db
from src.models import Order, WebhookProviderType
from src.models.order import OrderStatus, OrderType
from src.services.webhook_provider_service import WebhookProviderService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> WebhookProviderService:
    """Create service instance."""
    return WebhookProviderService(db)


# ============ TRON (TronGrid) ============


@router.post("/tron")
async def tron_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Receive TronGrid webhook notifications.

    TronGrid sends transaction events when addresses receive tokens.
    No signature verification - relies on endpoint secrecy.
    """
    try:
        body = await request.json()
        logger.info(f"TRON webhook received: {body}")

        # TronGrid event format
        event_type = body.get("event_type")
        if event_type != "TRANSACTION":
            return {"status": "ignored", "reason": "not a transaction event"}

        tx_data = body.get("transaction", {})
        tx_hash = tx_data.get("txID")
        if not tx_hash:
            return {"status": "ignored", "reason": "no tx_hash"}

        # Parse transfer data
        contract = tx_data.get("raw_data", {}).get("contract", [{}])[0]
        contract_type = contract.get("type")
        value = contract.get("parameter", {}).get("value", {})

        to_address = value.get("to_address")
        amount_raw = value.get("amount", 0)

        # Determine if TRX or TRC-20
        if contract_type == "TransferContract":
            # Native TRX transfer
            amount = Decimal(amount_raw) / Decimal(10**6)
            token_symbol = "TRX"
        elif contract_type == "TriggerSmartContract":
            # TRC-20 token transfer - parse from data field
            data = value.get("data", "")
            if data.startswith("a9059cbb"):  # transfer(address,uint256)
                to_address = _decode_tron_address(data[32:72])
                amount = Decimal(int(data[72:136], 16)) / Decimal(10**6)
                token_symbol = "USDT"  # Assume USDT for now
            else:
                return {"status": "ignored", "reason": "not a transfer"}
        else:
            return {"status": "ignored", "reason": f"unknown contract type: {contract_type}"}

        # Process the deposit
        await _process_deposit(
            db=db,
            chain_code="TRON",
            to_address=to_address,
            amount=amount,
            tx_hash=tx_hash,
            token_symbol=token_symbol,
        )

        return {"status": "ok"}

    except Exception as e:
        logger.exception(f"TRON webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Ethereum (Alchemy) ============


@router.post("/alchemy")
@router.post("/ethereum")  # Alias for backward compatibility
async def alchemy_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[WebhookProviderService, Depends(get_service)],
    x_alchemy_signature: Annotated[str | None, Header()] = None,
):
    """Receive Alchemy webhook notifications.

    Alchemy sends address activity webhooks for monitored addresses.
    Supports: Ethereum, Polygon, Arbitrum, Optimism, Base.
    """
    try:
        body = await request.body()

        # Get provider and verify signature
        provider = await service.get_provider_by_type_and_chain(
            WebhookProviderType.ALCHEMY, "ETHEREUM"
        )
        if provider and x_alchemy_signature:
            secrets = await service.get_decrypted_secrets(provider.id)  # type: ignore
            webhook_secret = secrets.get("webhook_secret") if secrets else None

            if webhook_secret:
                expected = hmac.new(
                    webhook_secret.encode(),
                    body,
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(expected, x_alchemy_signature):
                    raise HTTPException(status_code=401, detail="Invalid signature")

        data = await request.json()
        logger.info(f"Alchemy webhook received: {data}")

        webhook_type = data.get("type")
        if webhook_type != "ADDRESS_ACTIVITY":
            return {"status": "ignored", "reason": f"type: {webhook_type}"}

        event = data.get("event", {})
        activity = event.get("activity", [])

        # Determine chain from network field
        network = event.get("network", "ETH_MAINNET")
        chain_code = _alchemy_network_to_chain(network)

        for tx in activity:
            category = tx.get("category")
            if category not in ["external", "token"]:
                continue

            to_address = tx.get("toAddress")
            tx_hash = tx.get("hash")
            value = tx.get("value", 0)

            if category == "external":
                # Native token transfer (ETH, MATIC, etc.)
                amount = Decimal(str(value))
                token_symbol = _get_native_token(chain_code)
            else:
                # ERC-20 token transfer
                amount = Decimal(str(value))
                token_symbol = tx.get("asset", "USDT")

            await _process_deposit(
                db=db,
                chain_code=chain_code,
                to_address=to_address,
                amount=amount,
                tx_hash=tx_hash,
                token_symbol=token_symbol,
            )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Alchemy webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Solana (Helius) ============


@router.post("/helius")
@router.post("/solana")  # Alias for backward compatibility
async def helius_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[WebhookProviderService, Depends(get_service)],
    authorization: Annotated[str | None, Header()] = None,
):
    """Receive Helius webhook notifications.

    Helius sends transaction webhooks for monitored addresses on Solana.
    """
    try:
        # Get provider and verify authorization
        provider = await service.get_provider_by_type_and_chain(
            WebhookProviderType.HELIUS, "SOLANA"
        )
        if provider:
            secrets = await service.get_decrypted_secrets(provider.id)  # type: ignore
            webhook_secret = secrets.get("webhook_secret") if secrets else None

            if webhook_secret and authorization != webhook_secret:
                raise HTTPException(status_code=401, detail="Invalid authorization")

        body = await request.json()
        logger.info(f"Helius webhook received: {body}")

        # Helius sends array of transactions
        transactions = body if isinstance(body, list) else [body]

        for tx in transactions:
            tx_type = tx.get("type")
            if tx_type not in ["TRANSFER", "TOKEN_TRANSFER"]:
                continue

            tx_hash = tx.get("signature")
            if not tx_hash:
                continue

            # Parse native transfers
            native_transfers = tx.get("nativeTransfers", [])
            for transfer in native_transfers:
                to_address = transfer.get("toUserAccount")
                amount_lamports = transfer.get("amount", 0)
                amount = Decimal(amount_lamports) / Decimal(10**9)

                await _process_deposit(
                    db=db,
                    chain_code="SOLANA",
                    to_address=to_address,
                    amount=amount,
                    tx_hash=tx_hash,
                    token_symbol="SOL",
                )

            # Parse token transfers
            token_transfers = tx.get("tokenTransfers", [])
            for transfer in token_transfers:
                to_address = transfer.get("toUserAccount")
                amount = Decimal(str(transfer.get("tokenAmount", 0)))
                token_symbol = transfer.get("symbol", "USDT")

                await _process_deposit(
                    db=db,
                    chain_code="SOLANA",
                    to_address=to_address,
                    amount=amount,
                    tx_hash=tx_hash,
                    token_symbol=token_symbol,
                )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Helius webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ QuickNode ============


@router.post("/quicknode")
async def quicknode_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[WebhookProviderService, Depends(get_service)],
    x_qn_signature: Annotated[str | None, Header()] = None,
    x_qn_chain: Annotated[str | None, Header()] = None,
):
    """Receive QuickNode Streams notifications.

    QuickNode supports multiple chains with consistent format.
    """
    try:
        body = await request.body()

        # Verify signature if configured
        if x_qn_signature:
            # QuickNode uses HMAC-SHA256
            provider = await service.get_provider_by_type_and_chain(
                WebhookProviderType.QUICKNODE, x_qn_chain or "ETHEREUM"
            )
            if provider:
                secrets = await service.get_decrypted_secrets(provider.id)  # type: ignore
                webhook_secret = secrets.get("webhook_secret") if secrets else None

                if webhook_secret:
                    expected = hmac.new(
                        webhook_secret.encode(),
                        body,
                        hashlib.sha256,
                    ).hexdigest()
                    if not hmac.compare_digest(expected, x_qn_signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")

        data = await request.json()
        logger.info(f"QuickNode webhook received: {data}")

        # QuickNode stream format
        chain_code = _quicknode_chain_to_code(x_qn_chain or data.get("chain", "ethereum"))

        for match in data.get("matchedLogs", []):
            tx_hash = match.get("transactionHash")
            to_address = match.get("topics", [None, None, None])[2]  # ERC-20 transfer recipient
            if to_address:
                to_address = "0x" + to_address[-40:]

            # Parse amount from data
            amount_hex = match.get("data", "0x0")
            amount_raw = int(amount_hex, 16) if amount_hex else 0
            amount = Decimal(amount_raw) / Decimal(10**6)  # Assume 6 decimals for USDT

            await _process_deposit(
                db=db,
                chain_code=chain_code,
                to_address=to_address,
                amount=amount,
                tx_hash=tx_hash,
                token_symbol="USDT",
            )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"QuickNode webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Moralis ============


@router.post("/moralis")
async def moralis_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    service: Annotated[WebhookProviderService, Depends(get_service)],
    x_signature: Annotated[str | None, Header()] = None,
):
    """Receive Moralis Streams notifications.

    Moralis supports Ethereum, Polygon, BSC, Arbitrum, Avalanche.
    """
    try:
        body = await request.body()

        # Moralis uses signature verification
        if x_signature:
            # Find any Moralis provider to get secret
            providers, _ = await service.list_providers(
                provider_type=WebhookProviderType.MORALIS, is_enabled=True
            )
            if providers:
                secrets = await service.get_decrypted_secrets(providers[0].id)
                webhook_secret = secrets.get("webhook_secret") if secrets else None

                if webhook_secret:
                    expected = hmac.new(
                        webhook_secret.encode(),
                        body,
                        hashlib.sha256,
                    ).hexdigest()
                    if not hmac.compare_digest(expected, x_signature):
                        raise HTTPException(status_code=401, detail="Invalid signature")

        data = await request.json()
        logger.info(f"Moralis webhook received: {data}")

        # Moralis stream format
        chain_id = data.get("chainId")
        chain_code = _moralis_chain_id_to_code(chain_id)

        # ERC-20 transfers
        for transfer in data.get("erc20Transfers", []):
            to_address = transfer.get("to")
            tx_hash = transfer.get("transactionHash")
            amount = Decimal(str(transfer.get("valueWithDecimals", 0)))
            token_symbol = transfer.get("tokenSymbol", "USDT")

            await _process_deposit(
                db=db,
                chain_code=chain_code,
                to_address=to_address,
                amount=amount,
                tx_hash=tx_hash,
                token_symbol=token_symbol,
            )

        # Native transfers
        for tx in data.get("txs", []):
            to_address = tx.get("to")
            tx_hash = tx.get("hash")
            amount = Decimal(str(tx.get("value", 0))) / Decimal(10**18)
            token_symbol = _get_native_token(chain_code)

            await _process_deposit(
                db=db,
                chain_code=chain_code,
                to_address=to_address,
                amount=amount,
                tx_hash=tx_hash,
                token_symbol=token_symbol,
            )

        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Moralis webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Common Processing ============


async def _process_deposit(
    db: AsyncSession,
    chain_code: str,
    to_address: str | None,
    amount: Decimal,
    tx_hash: str | None,
    token_symbol: str,
    from_address: str | None = None,
):
    """Process a detected deposit transaction.

    Args:
        db: Database session
        chain_code: Chain code (TRON, ETHEREUM, SOLANA, etc.)
        to_address: Recipient address
        amount: Transfer amount
        tx_hash: Transaction hash
        token_symbol: Token symbol (USDT, ETH, etc.)
        from_address: Sender address (optional, for notification)
    """
    from src.tasks.telegram import trigger_address_income_notification

    if not to_address or not tx_hash:
        return

    # Normalize address (lowercase for EVM chains)
    if chain_code in ("ETHEREUM", "POLYGON", "ARBITRUM", "OPTIMISM", "BASE", "BSC", "AVALANCHE"):
        to_address = to_address.lower()

    # Find matching pending deposit order
    stmt = select(Order).where(
        and_(
            Order.order_type == OrderType.DEPOSIT,
            Order.status == OrderStatus.PENDING,
            Order.wallet_address == to_address,
        )
    )
    result = await db.execute(stmt)
    order = result.scalars().first()

    if not order:
        logger.debug(f"No pending order for address {to_address}")
        return

    # Verify amount matches (allow small tolerance for fees)
    expected = Decimal(str(order.amount))
    if amount < expected * Decimal("0.99"):
        logger.warning(
            f"Amount mismatch for order {order.order_no}: expected {expected}, got {amount}"
        )
        return

    # Update order
    order.tx_hash = tx_hash
    order.status = OrderStatus.CONFIRMING
    order.actual_amount = str(amount)
    db.add(order)
    await db.commit()

    logger.info(
        f"Deposit detected for order {order.order_no}: "
        f"{amount} {token_symbol} on {chain_code}, tx={tx_hash}"
    )

    # Send Telegram notification for address income
    trigger_address_income_notification(
        merchant_id=order.merchant_id,
        address=to_address,
        amount=amount,
        token=token_symbol,
        chain=chain_code,
        tx_hash=tx_hash,
        from_address=from_address,
    )


# ============ Helper Functions ============


def _decode_tron_address(hex_addr: str) -> str:
    """Decode TRON address from hex format."""
    try:
        import base58

        hex_addr = hex_addr.lstrip("0")
        if len(hex_addr) < 40:
            hex_addr = "0" * (40 - len(hex_addr)) + hex_addr
        hex_addr = "41" + hex_addr

        addr_bytes = bytes.fromhex(hex_addr)
        hash1 = hashlib.sha256(addr_bytes).digest()
        hash2 = hashlib.sha256(hash1).digest()
        checksum = hash2[:4]

        return base58.b58encode(addr_bytes + checksum).decode()
    except Exception:
        return ""


def _alchemy_network_to_chain(network: str) -> str:
    """Convert Alchemy network ID to chain code."""
    mapping = {
        "ETH_MAINNET": "ETHEREUM",
        "ETH_GOERLI": "ETHEREUM",
        "ETH_SEPOLIA": "ETHEREUM",
        "MATIC_MAINNET": "POLYGON",
        "MATIC_MUMBAI": "POLYGON",
        "ARB_MAINNET": "ARBITRUM",
        "ARB_GOERLI": "ARBITRUM",
        "OPT_MAINNET": "OPTIMISM",
        "OPT_GOERLI": "OPTIMISM",
        "BASE_MAINNET": "BASE",
        "BASE_GOERLI": "BASE",
    }
    return mapping.get(network, "ETHEREUM")


def _quicknode_chain_to_code(chain: str) -> str:
    """Convert QuickNode chain name to chain code."""
    mapping = {
        "ethereum": "ETHEREUM",
        "polygon": "POLYGON",
        "bsc": "BSC",
        "arbitrum": "ARBITRUM",
        "solana": "SOLANA",
        "tron": "TRON",
    }
    return mapping.get(chain.lower(), "ETHEREUM")


def _moralis_chain_id_to_code(chain_id: str | None) -> str:
    """Convert Moralis chain ID to chain code."""
    mapping = {
        "0x1": "ETHEREUM",
        "0x89": "POLYGON",
        "0x38": "BSC",
        "0xa4b1": "ARBITRUM",
        "0xa86a": "AVALANCHE",
    }
    return mapping.get(chain_id or "", "ETHEREUM")


def _get_native_token(chain_code: str) -> str:
    """Get native token symbol for a chain."""
    mapping = {
        "ETHEREUM": "ETH",
        "POLYGON": "MATIC",
        "BSC": "BNB",
        "ARBITRUM": "ETH",
        "OPTIMISM": "ETH",
        "BASE": "ETH",
        "AVALANCHE": "AVAX",
        "SOLANA": "SOL",
        "TRON": "TRX",
    }
    return mapping.get(chain_code, "ETH")


# ============ Clerk (User Events) ============


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    svix_id: str | None = Header(None, alias="svix-id"),
    svix_timestamp: str | None = Header(None, alias="svix-timestamp"),
    svix_signature: str | None = Header(None, alias="svix-signature"),
):
    """Handle incoming Clerk webhook events.

    Primarily handles:
    - user.created: Create local user record with role from invitation metadata
    - user.deleted: Deactivate local user

    The role is determined from the invitation's public_metadata which
    is set when sending the invitation via our API.

    TODO: Implement Svix signature verification for production.
    """
    import json

    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = payload.get("type")
    data = payload.get("data", {})

    if event_type == "user.created":
        await _handle_clerk_user_created(db, data)
    elif event_type == "user.deleted":
        await _handle_clerk_user_deleted(db, data)

    return {"received": True}


async def _handle_clerk_user_created(db: AsyncSession, data: dict) -> None:
    """Handle user.created event from Clerk.

    This is called when a user completes registration via an invitation link.
    The role and other metadata are extracted from the invitation's public_metadata.
    """
    from datetime import UTC, datetime

    from src.models.user import User, UserRole, generate_api_key

    clerk_id = data.get("id")
    if not clerk_id:
        return

    # Get email
    email_addresses = data.get("email_addresses", [])
    primary_email_id = data.get("primary_email_address_id")
    email = ""
    for addr in email_addresses:
        if addr.get("id") == primary_email_id:
            email = addr.get("email_address", "")
            break
    if not email and email_addresses:
        email = email_addresses[0].get("email_address", "")

    # Get username
    username = data.get("username")

    # Get role and metadata from public_metadata (set during invitation)
    public_metadata = data.get("public_metadata", {})
    role_str = public_metadata.get("role", "merchant")  # Default to merchant
    parent_id = public_metadata.get("parent_id")
    permissions = public_metadata.get("permissions", [])

    # Convert role string to enum
    try:
        role = UserRole(role_str)
    except ValueError:
        role = UserRole.MERCHANT

    # Check if user already exists
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    existing = result.scalar_one_or_none()

    if existing:
        # User already exists, update if needed
        existing.email = email
        if username:
            existing.username = username
        existing.updated_at = datetime.now(UTC)
        db.add(existing)
        await db.commit()
        return

    # Create new user
    new_user = User(
        clerk_id=clerk_id,
        email=email,
        username=username,
        role=role,
        is_active=True,
        parent_id=parent_id if role == UserRole.SUPPORT else None,
        permissions=permissions if role == UserRole.SUPPORT else [],
    )

    # Generate API keys for merchants
    if role == UserRole.MERCHANT:
        new_user.deposit_key = generate_api_key()
        new_user.withdraw_key = generate_api_key()

    db.add(new_user)
    await db.commit()
    logger.info(f"Created user from Clerk webhook: {email} with role {role}")


async def _handle_clerk_user_deleted(db: AsyncSession, data: dict) -> None:
    """Handle user.deleted event from Clerk.

    When a user is deleted from Clerk, we deactivate them locally
    rather than deleting, to preserve audit trails.
    """
    from datetime import UTC, datetime

    from src.models.user import User

    clerk_id = data.get("id")
    if not clerk_id:
        return

    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if user:
        user.is_active = False
        user.updated_at = datetime.now(UTC)
        db.add(user)
        await db.commit()
        logger.info(f"Deactivated user from Clerk webhook: {user.email}")
