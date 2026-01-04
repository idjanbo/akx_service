"""Update and optimize chains and tokens data.

Run with: uv run python -m src.scripts.update_chains_tokens_data
"""

import asyncio

from sqlmodel import select

from src.db.engine import async_session_factory, close_db
from src.models.chain import Chain
from src.models.token import Token, TokenChainSupport

# Optimized chains data with corrections (following Binance naming convention)
CHAINS_UPDATES = {
    "TRON": {
        "name": "TRON (TRC20)",
        "description": "高吞吐量公链，支持 TRC-20 代币，交易费用低",
        "remark": "主要用于 USDT 交易",
        "rpc_url": "https://api.trongrid.io",
        "explorer_url": "https://tronscan.org",
        "native_token": "TRX",
        "confirmation_blocks": 19,
        "sort_order": 1,
    },
    "ETH": {
        "name": "Ethereum (ERC20)",
        "description": "领先的智能合约平台，拥有庞大的 DeFi 生态系统",
        "remark": "Gas 费较高，但更安全",
        "rpc_url": "https://mainnet.infura.io/v3/YOUR_PROJECT_ID",
        "explorer_url": "https://etherscan.io",
        "native_token": "ETH",
        "confirmation_blocks": 12,
        "sort_order": 2,
    },
    "BSC": {
        "name": "BNB Smart Chain (BEP20)",
        "description": "兼容 EVM 的高性能公链，交易费用低",
        "remark": "快速且经济的以太坊替代方案",
        "rpc_url": "https://bsc-dataseed.binance.org",
        "explorer_url": "https://bscscan.com",
        "native_token": "BNB",
        "confirmation_blocks": 15,
        "sort_order": 3,
    },
    "SOL": {
        "name": "Solana (SPL)",
        "description": "高性能区块链，亚秒级确认速度",
        "remark": "交易速度极快，生态不断增长",
        "rpc_url": "https://api.mainnet-beta.solana.com",
        "explorer_url": "https://solscan.io",
        "native_token": "SOL",
        "confirmation_blocks": 1,
        "sort_order": 4,
    },
    "TON": {
        "name": "TON (Jetton)",
        "description": "Telegram 的区块链，快速且可扩展",
        "remark": "与 Telegram 集成，快速确认",
        "rpc_url": "https://toncenter.com/api/v2/jsonRPC",
        "explorer_url": "https://tonscan.org",
        "native_token": "TON",
        "confirmation_blocks": 1,
        "sort_order": 5,
    },
}

# Optimized tokens data with corrections
TOKENS_UPDATES = {
    "USDT": {
        "symbol": "USDT",
        "name": "USDT",
        "full_name": "泰达币",
        "description": "市值最大的美元稳定币",
        "remark": "主要结算货币",
        "decimals": 6,
        "icon_url": "https://cryptologos.cc/logos/tether-usdt-logo.png",
        "is_stablecoin": True,
        "sort_order": 1,
    },
    "USDC": {
        "symbol": "USDC",
        "name": "USDC",
        "full_name": "美元硬币",
        "description": "Circle 发行的合规美元稳定币",
        "remark": "备选稳定币",
        "decimals": 6,
        "icon_url": "https://cryptologos.cc/logos/usd-coin-usdc-logo.png",
        "is_stablecoin": True,
        "sort_order": 2,
    },
    "TRX": {
        "symbol": "TRX",
        "name": "TRX",
        "full_name": "波场币",
        "description": "TRON 区块链原生代币",
        "remark": "用于支付 TRON 网络 Gas 费",
        "decimals": 6,
        "icon_url": "https://cryptologos.cc/logos/tron-trx-logo.png",
        "is_stablecoin": False,
        "sort_order": 3,
    },
    "SOL": {
        "symbol": "SOL",
        "name": "SOL",
        "full_name": "Solana 币",
        "description": "Solana 区块链原生代币",
        "remark": "用于支付 Solana 网络 Gas 费",
        "decimals": 9,
        "icon_url": "https://cryptologos.cc/logos/solana-sol-logo.png",
        "is_stablecoin": False,
        "sort_order": 4,
    },
    "ETH": {
        "symbol": "ETH",
        "name": "ETH",
        "full_name": "以太币",
        "description": "以太坊区块链原生代币",
        "remark": "用于支付以太坊网络 Gas 费",
        "decimals": 18,
        "icon_url": "https://cryptologos.cc/logos/ethereum-eth-logo.png",
        "is_stablecoin": False,
        "sort_order": 5,
    },
    "BNB": {
        "symbol": "BNB",
        "name": "BNB",
        "full_name": "币安币",
        "description": "BNB Chain 原生代币",
        "remark": "用于支付 BNB Chain 网络 Gas 费",
        "decimals": 18,
        "icon_url": "https://cryptologos.cc/logos/bnb-bnb-logo.png",
        "is_stablecoin": False,
        "sort_order": 6,
    },
    "TON": {
        "symbol": "TON",
        "name": "TON",
        "full_name": "TON 币",
        "description": "TON 区块链原生代币",
        "remark": "用于支付 TON 网络 Gas 费",
        "decimals": 9,
        "icon_url": "https://cryptologos.cc/logos/toncoin-ton-logo.png",
        "is_stablecoin": False,
        "sort_order": 7,
    },
}

# Update token-chain support configurations
TOKEN_CHAIN_UPDATES = {
    # USDT on TRON (TRC-20)
    ("USDT", "TRON"): {
        "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "1.0",
    },
    # USDT on Ethereum (ERC-20)
    ("USDT", "ETH"): {
        "contract_address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "is_native": False,
        "min_deposit": "10.0",
        "min_withdrawal": "50.0",
        "withdrawal_fee": "5.0",
    },
    # USDT on BNB Chain (BEP-20)
    ("USDT", "BSC"): {
        "contract_address": "0x55d398326f99059fF775485246999027B3197955",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.5",
    },
    # USDT on Solana (SPL)
    ("USDT", "SOL"): {
        "contract_address": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.1",
    },
    # USDT on TON (Jetton)
    ("USDT", "TON"): {
        "contract_address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.1",
    },
    # USDC on TRON (TRC-20)
    ("USDC", "TRON"): {
        "contract_address": "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "1.0",
    },
    # USDC on Ethereum (ERC-20)
    ("USDC", "ETH"): {
        "contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "is_native": False,
        "min_deposit": "10.0",
        "min_withdrawal": "50.0",
        "withdrawal_fee": "5.0",
    },
    # USDC on BNB Chain (BEP-20)
    ("USDC", "BSC"): {
        "contract_address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.5",
    },
    # USDC on Solana (SPL)
    ("USDC", "SOL"): {
        "contract_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.1",
    },
    # USDC on TON (Jetton)
    ("USDC", "TON"): {
        "contract_address": "EQC_1YoM8RBixN95lz7odcF3Vrkc_N8Ne7gQi7Abtlet_Efi",
        "is_native": False,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.1",
    },
    # Native tokens (no contract address)
    ("TRX", "TRON"): {
        "contract_address": "",
        "is_native": True,
        "min_deposit": "10.0",
        "min_withdrawal": "100.0",
        "withdrawal_fee": "1.0",
    },
    ("SOL", "SOL"): {
        "contract_address": "",
        "is_native": True,
        "min_deposit": "0.01",
        "min_withdrawal": "0.1",
        "withdrawal_fee": "0.001",
    },
    ("ETH", "ETH"): {
        "contract_address": "",
        "is_native": True,
        "min_deposit": "0.001",
        "min_withdrawal": "0.01",
        "withdrawal_fee": "0.001",
    },
    ("BNB", "BSC"): {
        "contract_address": "",
        "is_native": True,
        "min_deposit": "0.001",
        "min_withdrawal": "0.01",
        "withdrawal_fee": "0.0001",
    },
    ("TON", "TON"): {
        "contract_address": "",
        "is_native": True,
        "min_deposit": "1.0",
        "min_withdrawal": "10.0",
        "withdrawal_fee": "0.1",
    },
}


async def update_data():
    """Update chains, tokens, and token-chain support data."""
    async with async_session_factory() as session:
        print("开始更新链和代币数据...\n")

        # 1. Update chains
        print("1. 更新区块链配置...")
        chain_count = 0
        for code, updates in CHAINS_UPDATES.items():
            result = await session.execute(select(Chain).where(Chain.code == code))
            chain = result.scalars().first()

            if chain:
                for field, value in updates.items():
                    setattr(chain, field, value)

                from datetime import UTC, datetime

                chain.updated_at = datetime.now(UTC)
                chain_count += 1
                print(f"   ✓ 已更新链: {chain.name} ({code})")

        await session.commit()
        print(f"✓ 区块链配置已更新: {chain_count} 条记录\n")

        # 2. Update tokens
        print("2. 更新代币配置...")
        token_count = 0
        for code, updates in TOKENS_UPDATES.items():
            result = await session.execute(select(Token).where(Token.code == code))
            token = result.scalars().first()

            if token:
                for field, value in updates.items():
                    setattr(token, field, value)

                from datetime import UTC, datetime

                token.updated_at = datetime.now(UTC)
                token_count += 1
                print(f"   ✓ 已更新代币: {token.name} ({code})")

        await session.commit()
        print(f"✓ 代币配置已更新: {token_count} 条记录\n")

        # 3. Update token-chain supports
        print("3. 更新代币-链支持配置...")
        support_count = 0

        # Get all tokens and chains for mapping
        tokens_result = await session.execute(select(Token))
        tokens = {t.code: t for t in tokens_result.scalars().all()}

        chains_result = await session.execute(select(Chain))
        chains = {c.code: c for c in chains_result.scalars().all()}

        for (token_code, chain_code), updates in TOKEN_CHAIN_UPDATES.items():
            if token_code not in tokens or chain_code not in chains:
                continue

            token = tokens[token_code]
            chain = chains[chain_code]

            result = await session.execute(
                select(TokenChainSupport)
                .where(TokenChainSupport.token_id == token.id)
                .where(TokenChainSupport.chain_id == chain.id)
            )
            support = result.scalars().first()

            if support:
                for field, value in updates.items():
                    setattr(support, field, value)

                from datetime import UTC, datetime

                support.updated_at = datetime.now(UTC)
                support_count += 1
                print(f"   ✓ 已更新支持: {token_code} on {chain_code}")

        await session.commit()
        print(f"✓ 代币-链支持配置已更新: {support_count} 条记录\n")

        print("=" * 60)
        print("✓ 所有数据更新完成!")
        print("=" * 60)
        print("\n总结:")
        print(f"  - {chain_count} 个区块链配置已优化")
        print(f"  - {token_count} 个代币配置已优化")
        print(f"  - {support_count} 个代币-链支持配置已优化")
        print("\n数据已优化为中文描述，便于理解和使用。")


async def main():
    """Main function to run update and cleanup."""
    try:
        await update_data()
    finally:
        # Ensure database connections are properly closed
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
