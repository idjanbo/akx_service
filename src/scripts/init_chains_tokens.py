"""Initialize system chains and tokens.

This script populates the database with predefined chains and tokens
according to the system requirements.

Chains:
- TRON
- Ethereum
- BNB Chain
- Solana
- The Open Network (TON)

Tokens:
- USDT (supports: TRON, Ethereum, BNB Chain, Solana, TON)
- USDC (supports: TRON, Ethereum, BNB Chain, Solana, TON)
- TRX (supports: TRON)
- SOL (supports: Solana)
- ETH (supports: Ethereum)
- BNB (supports: BNB Chain)
- TON (supports: The Open Network)
- BTC (Bitcoin - can be added later with specific chain support)

Run with: uv run python -m src.scripts.init_chains_tokens
"""

import asyncio

from sqlmodel import select

from src.db.engine import async_session_factory, close_db
from src.models.chain import Chain
from src.models.token import Token, TokenChainSupport

# Predefined chains configuration
CHAINS = [
    {
        "code": "TRON",
        "name": "TRON (TRC20)",
        "description": "High-throughput blockchain supporting TRC-20 tokens with low fees",
        "remark": "Primary chain for USDT transactions",
        "is_enabled": True,
        "sort_order": 1,
        "rpc_url": "https://api.trongrid.io",
        "explorer_url": "https://tronscan.org",
        "native_token": "TRX",
        "confirmation_blocks": 19,
    },
    {
        "code": "ETH",
        "name": "Ethereum (ERC20)",
        "description": "Leading smart contract platform with extensive DeFi ecosystem",
        "remark": "Higher gas fees, more secure",
        "is_enabled": True,
        "sort_order": 2,
        "rpc_url": "https://mainnet.infura.io/v3/YOUR_PROJECT_ID",
        "explorer_url": "https://etherscan.io",
        "native_token": "ETH",
        "confirmation_blocks": 12,
    },
    {
        "code": "BSC",
        "name": "BNB Smart Chain (BEP20)",
        "description": "Binance Smart Chain with EVM compatibility and low fees",
        "remark": "Fast and cost-effective alternative to Ethereum",
        "is_enabled": True,
        "sort_order": 3,
        "rpc_url": "https://bsc-dataseed.binance.org",
        "explorer_url": "https://bscscan.com",
        "native_token": "BNB",
        "confirmation_blocks": 15,
    },
    {
        "code": "SOL",
        "name": "Solana (SPL)",
        "description": "High-performance blockchain with sub-second finality",
        "remark": "Very fast transactions, growing ecosystem",
        "is_enabled": True,
        "sort_order": 4,
        "rpc_url": "https://api.mainnet-beta.solana.com",
        "explorer_url": "https://solscan.io",
        "native_token": "SOL",
        "confirmation_blocks": 1,
    },
    {
        "code": "TON",
        "name": "TON (Jetton)",
        "description": "Telegram's blockchain with fast and scalable architecture",
        "remark": "Telegram integration, fast finality",
        "is_enabled": True,
        "sort_order": 5,
        "rpc_url": "https://toncenter.com/api/v2/jsonRPC",
        "explorer_url": "https://tonscan.org",
        "native_token": "TON",
        "confirmation_blocks": 1,
    },
]

# Predefined tokens configuration
TOKENS = [
    {
        "code": "USDT",
        "symbol": "USDT",
        "name": "Tether USD",
        "full_name": "Tether USD Stablecoin",
        "description": "Leading USD-pegged stablecoin with highest market cap",
        "remark": "Primary settlement currency",
        "is_enabled": True,
        "sort_order": 1,
        "decimals": 6,
        "is_stablecoin": True,
    },
    {
        "code": "USDC",
        "symbol": "USDC",
        "name": "USD Coin",
        "full_name": "USD Coin Stablecoin",
        "description": "Fully regulated USD stablecoin by Circle",
        "remark": "Alternative stablecoin option",
        "is_enabled": True,
        "sort_order": 2,
        "decimals": 6,
        "is_stablecoin": True,
    },
    {
        "code": "TRX",
        "symbol": "TRX",
        "name": "TRON",
        "full_name": "TRON Native Token",
        "description": "Native cryptocurrency of TRON blockchain",
        "remark": "Used for gas fees on TRON",
        "is_enabled": True,
        "sort_order": 3,
        "decimals": 6,
        "is_stablecoin": False,
    },
    {
        "code": "SOL",
        "symbol": "SOL",
        "name": "Solana",
        "full_name": "Solana Native Token",
        "description": "Native cryptocurrency of Solana blockchain",
        "remark": "Used for gas fees on Solana",
        "is_enabled": True,
        "sort_order": 4,
        "decimals": 9,
        "is_stablecoin": False,
    },
    {
        "code": "ETH",
        "symbol": "ETH",
        "name": "Ethereum",
        "full_name": "Ethereum Native Token",
        "description": "Native cryptocurrency of Ethereum blockchain",
        "remark": "Used for gas fees on Ethereum",
        "is_enabled": True,
        "sort_order": 5,
        "decimals": 18,
        "is_stablecoin": False,
    },
    {
        "code": "BNB",
        "symbol": "BNB",
        "name": "BNB",
        "full_name": "Binance Coin",
        "description": "Native cryptocurrency of BNB Chain",
        "remark": "Used for gas fees on BNB Chain",
        "is_enabled": True,
        "sort_order": 6,
        "decimals": 18,
        "is_stablecoin": False,
    },
    {
        "code": "TON",
        "symbol": "TON",
        "name": "Toncoin",
        "full_name": "The Open Network Token",
        "description": "Native cryptocurrency of TON blockchain",
        "remark": "Used for gas fees on TON",
        "is_enabled": True,
        "sort_order": 7,
        "decimals": 9,
        "is_stablecoin": False,
    },
]

# Token-Chain support mappings
# Format: (token_code, chain_code, contract_address, is_native, min_deposit, min_withdrawal,
#  withdrawal_fee)
TOKEN_CHAIN_MAPPINGS = [
    # USDT supports
    ("USDT", "TRON", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", False, "1.0", "10.0", "1.0"),
    (
        "USDT",
        "ETHEREUM",
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        False,
        "10.0",
        "50.0",
        "5.0",
    ),
    (
        "USDT",
        "BNB_CHAIN",
        "0x55d398326f99059fF775485246999027B3197955",
        False,
        "1.0",
        "10.0",
        "0.5",
    ),
    ("USDT", "SOLANA", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", False, "1.0", "10.0", "0.1"),
    (
        "USDT",
        "TON",
        "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
        False,
        "1.0",
        "10.0",
        "0.5",
    ),
    # USDC supports
    ("USDC", "TRON", "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8", False, "1.0", "10.0", "1.0"),
    (
        "USDC",
        "ETHEREUM",
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        False,
        "10.0",
        "50.0",
        "5.0",
    ),
    (
        "USDC",
        "BNB_CHAIN",
        "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        False,
        "1.0",
        "10.0",
        "0.5",
    ),
    ("USDC", "SOLANA", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", False, "1.0", "10.0", "0.1"),
    (
        "USDC",
        "TON",
        "EQC_1YoM8RBixN95lz7odcF3Vrkc_N8Ne7gQi7Abtlet_Efi",
        False,
        "1.0",
        "10.0",
        "0.5",
    ),
    # Native tokens
    ("TRX", "TRON", "", True, "10.0", "100.0", "1.0"),
    ("SOL", "SOLANA", "", True, "0.01", "0.1", "0.001"),
    ("ETH", "ETHEREUM", "", True, "0.001", "0.01", "0.001"),
    ("BNB", "BNB_CHAIN", "", True, "0.001", "0.01", "0.0001"),
    ("TON", "TON", "", True, "1.0", "10.0", "0.1"),
]


async def init_chains_tokens():
    """Initialize chains and tokens in the database."""
    async with async_session_factory() as session:
        print("Starting chains and tokens initialization...")

        # 1. Create chains
        print("\n1. Creating chains...")
        chain_map = {}  # Store created chains by code

        for chain_data in CHAINS:
            # Check if chain already exists
            result = await session.execute(select(Chain).where(Chain.code == chain_data["code"]))
            existing_chain = result.scalars().first()

            if existing_chain:
                print(f"   - Chain {chain_data['code']} already exists, skipping...")
                chain_map[chain_data["code"]] = existing_chain
                continue

            chain = Chain(**chain_data)
            session.add(chain)
            chain_map[chain_data["code"]] = chain
            print(f"   + Created chain: {chain_data['name']} ({chain_data['code']})")

        await session.commit()
        print(f"✓ Chains initialized: {len(chain_map)} chains")

        # 2. Create tokens
        print("\n2. Creating tokens...")
        token_map = {}  # Store created tokens by code

        for token_data in TOKENS:
            # Check if token already exists
            result = await session.execute(select(Token).where(Token.code == token_data["code"]))
            existing_token = result.scalars().first()

            if existing_token:
                print(f"   - Token {token_data['code']} already exists, skipping...")
                token_map[token_data["code"]] = existing_token
                continue

            token = Token(**token_data)
            session.add(token)
            token_map[token_data["code"]] = token
            print(f"   + Created token: {token_data['name']} ({token_data['code']})")

        await session.commit()
        print(f"✓ Tokens initialized: {len(token_map)} tokens")

        # Refresh to get IDs
        for token in token_map.values():
            await session.refresh(token)
        for chain in chain_map.values():
            await session.refresh(chain)

        # 3. Create token-chain supports
        print("\n3. Creating token-chain support mappings...")
        support_count = 0

        for (
            token_code,
            chain_code,
            contract_addr,
            is_native,
            min_dep,
            min_with,
            with_fee,
        ) in TOKEN_CHAIN_MAPPINGS:
            token = token_map.get(token_code)
            chain = chain_map.get(chain_code)

            if not token or not chain:
                print(
                    f"   ! Warning: Token {token_code} or Chain {chain_code} not found, skipping..."
                )
                continue

            # Check if support already exists
            result = await session.execute(
                select(TokenChainSupport)
                .where(TokenChainSupport.token_id == token.id)
                .where(TokenChainSupport.chain_id == chain.id)
            )
            existing_support = result.scalars().first()

            if existing_support:
                print(f"   - Support {token_code} on {chain_code} already exists, skipping...")
                continue

            support = TokenChainSupport(
                token_id=token.id,
                chain_id=chain.id,
                contract_address=contract_addr,
                is_enabled=True,
                is_native=is_native,
                min_deposit=min_dep,
                min_withdrawal=min_with,
                withdrawal_fee=with_fee,
            )
            session.add(support)
            support_count += 1
            native_label = " (native)" if is_native else ""
            print(f"   + Created support: {token_code} on {chain_code}{native_label}")

        await session.commit()
        print(f"✓ Token-chain supports initialized: {support_count} mappings")

        print("\n" + "=" * 60)
        print("✓ All chains and tokens initialized successfully!")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - {len(chain_map)} chains created")
        print(f"  - {len(token_map)} tokens created")
        print(f"  - {support_count} token-chain support mappings created")
        print("\nYou can now use the API to manage chains, tokens, and their relationships.")


async def main():
    """Main function to run initialization and cleanup."""
    try:
        await init_chains_tokens()
    finally:
        # Ensure database connections are properly closed
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
