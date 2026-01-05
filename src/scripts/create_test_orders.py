"""Create test deposit and withdrawal orders.

This script creates sample orders for testing the order management system.

Run with: uv run python -m src.scripts.create_test_orders
"""

import asyncio
import random
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlmodel import select

from src.db.engine import close_db, get_session
from src.models.order import (
    CallbackStatus,
    Order,
    OrderStatus,
    OrderType,
    generate_order_no,
)
from src.models.user import User, UserRole

# Sample wallet addresses for different chains
SAMPLE_ADDRESSES = {
    "tron": [
        "TYigsqRvieWnD4JbPpPa8UbemhQwk9sodj",
        "TXzW9kHMBnD8vNmCpQwk5sodj9VaLkJpR3",
        "TNPeeaaFB7K9cmo4uQpcU32zGK8G1NYqeL",
    ],
    "ethereum": [
        "0x742d35Cc6634C0532925a3b844Bc454e59570bEb",
        "0x8ba1f109551bD432803012645Hc136E1Ba45678",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    ],
    "solana": [
        "DRpbCBMxVnDK7maPM5tGv6MvB3v1sRMC86PZ8okm21hy",
        "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    ],
}

# Sample tokens and their supported chains
TOKEN_CHAINS = {
    "USDT": ["tron", "ethereum", "solana"],
    "USDC": ["tron", "ethereum", "solana"],
    "ETH": ["ethereum"],
    "TRX": ["tron"],
    "SOL": ["solana"],
}


# Sample transaction hashes
def generate_tx_hash(chain: str) -> str:
    """Generate a sample transaction hash based on chain."""
    if chain == "tron":
        return secrets.token_hex(32)
    elif chain == "ethereum":
        return "0x" + secrets.token_hex(32)
    elif chain == "solana":
        # Solana uses base58, but for demo we use hex
        return secrets.token_hex(32)
    return secrets.token_hex(32)


def generate_out_trade_no(prefix: str) -> str:
    """Generate external trade number."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4).upper()
    return f"{prefix}{timestamp}{random_suffix}"


async def get_or_create_merchant(db) -> User:
    """Get existing merchant or create one for testing."""
    # Try to find an existing merchant
    result = await db.execute(select(User).where(User.role == UserRole.MERCHANT).limit(1))
    merchant = result.scalar_one_or_none()

    if merchant:
        print(f"Using existing merchant: {merchant.email} (ID: {merchant.id})")
        return merchant

    # Create a test merchant
    merchant = User(
        clerk_id=f"test_clerk_{secrets.token_hex(8)}",
        email="test_merchant@example.com",
        role=UserRole.MERCHANT,
        deposit_key=secrets.token_hex(32),
        withdraw_key=secrets.token_hex(32),
        is_active=True,
    )
    db.add(merchant)
    await db.flush()
    print(f"Created test merchant: {merchant.email} (ID: {merchant.id})")
    return merchant


async def create_deposit_orders(db, merchant: User, count: int = 10) -> list[Order]:
    """Create sample deposit orders."""
    orders = []

    for i in range(count):
        # Random token and chain
        token = random.choice(list(TOKEN_CHAINS.keys()))
        chain = random.choice(TOKEN_CHAINS[token])

        # Random amount
        amount = Decimal(str(round(random.uniform(10, 1000), 2)))

        # Random status
        status_weights = [
            (OrderStatus.PENDING, 0.2),
            (OrderStatus.CONFIRMING, 0.1),
            (OrderStatus.SUCCESS, 0.5),
            (OrderStatus.EXPIRED, 0.2),
        ]
        status = random.choices(
            [s[0] for s in status_weights],
            weights=[s[1] for s in status_weights],
        )[0]

        # Create order
        order = Order(
            order_no=generate_order_no(OrderType.DEPOSIT),
            out_trade_no=generate_out_trade_no("DEP"),
            order_type=OrderType.DEPOSIT,
            merchant_id=merchant.id,
            token=token,
            chain=chain,
            amount=amount,
            fee=Decimal("0"),
            net_amount=amount,
            wallet_address=random.choice(SAMPLE_ADDRESSES.get(chain, SAMPLE_ADDRESSES["tron"])),
            status=status,
            callback_url="https://example.com/api/callback/deposit",
            callback_status=CallbackStatus.SUCCESS
            if status == OrderStatus.SUCCESS
            else CallbackStatus.PENDING,
            extra_data=f'{{"user_id": {random.randint(1000, 9999)}}}',
            expire_time=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC) - timedelta(hours=random.randint(0, 48)),
        )

        # Add tx_hash and confirmations for completed orders
        if status in [OrderStatus.CONFIRMING, OrderStatus.SUCCESS]:
            order.tx_hash = generate_tx_hash(chain)
            order.confirmations = 19 if status == OrderStatus.SUCCESS else random.randint(1, 18)

        if status == OrderStatus.SUCCESS:
            order.completed_at = order.created_at + timedelta(minutes=random.randint(1, 10))

        orders.append(order)
        db.add(order)

    await db.flush()
    print(f"Created {len(orders)} deposit orders")
    return orders


async def create_withdrawal_orders(db, merchant: User, count: int = 10) -> list[Order]:
    """Create sample withdrawal orders."""
    orders = []

    for i in range(count):
        # Random token and chain
        token = random.choice(list(TOKEN_CHAINS.keys()))
        chain = random.choice(TOKEN_CHAINS[token])

        # Random amount
        amount = Decimal(str(round(random.uniform(50, 500), 2)))

        # Fee calculation (1% with minimum 1.0)
        fee = max(Decimal("1.0"), amount * Decimal("0.01"))
        net_amount = amount - fee

        # Random status
        status_weights = [
            (OrderStatus.PENDING, 0.2),
            (OrderStatus.PROCESSING, 0.1),
            (OrderStatus.SUCCESS, 0.5),
            (OrderStatus.FAILED, 0.2),
        ]
        status = random.choices(
            [s[0] for s in status_weights],
            weights=[s[1] for s in status_weights],
        )[0]

        # Create order
        order = Order(
            order_no=generate_order_no(OrderType.WITHDRAW),
            out_trade_no=generate_out_trade_no("WD"),
            order_type=OrderType.WITHDRAW,
            merchant_id=merchant.id,
            token=token,
            chain=chain,
            amount=amount,
            fee=fee,
            net_amount=net_amount,
            wallet_address=random.choice(SAMPLE_ADDRESSES.get(chain, SAMPLE_ADDRESSES["tron"])),
            to_address=random.choice(SAMPLE_ADDRESSES.get(chain, SAMPLE_ADDRESSES["tron"])),
            status=status,
            callback_url="https://example.com/api/callback/withdraw",
            callback_status=CallbackStatus.SUCCESS
            if status in [OrderStatus.SUCCESS, OrderStatus.FAILED]
            else CallbackStatus.PENDING,
            extra_data=f'{{"user_id": {random.randint(1000, 9999)}}}',
            created_at=datetime.now(UTC) - timedelta(hours=random.randint(0, 48)),
        )

        # Add tx_hash and confirmations for completed orders
        if status in [OrderStatus.PROCESSING, OrderStatus.SUCCESS]:
            order.tx_hash = generate_tx_hash(chain)
            order.confirmations = 19 if status == OrderStatus.SUCCESS else random.randint(1, 18)

        if status in [OrderStatus.SUCCESS, OrderStatus.FAILED]:
            order.completed_at = order.created_at + timedelta(minutes=random.randint(5, 30))

        # Add remark for failed orders
        if status == OrderStatus.FAILED:
            order.remark = random.choice(
                [
                    "Insufficient balance",
                    "Invalid address",
                    "Network congestion, transaction failed",
                ]
            )

        orders.append(order)
        db.add(order)

    await db.flush()
    print(f"Created {len(orders)} withdrawal orders")
    return orders


async def main():
    """Main function to create test orders."""
    print("=" * 60)
    print("Creating test orders...")
    print("=" * 60)

    try:
        async with get_session() as db:
            # Get or create merchant
            merchant = await get_or_create_merchant(db)

            # Create deposit orders
            await create_deposit_orders(db, merchant, count=15)

            # Create withdrawal orders
            await create_withdrawal_orders(db, merchant, count=15)

            # Commit all changes
            await db.commit()

            print("=" * 60)
            print("Test orders created successfully!")
            print("=" * 60)

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
