# 链和币种管理系统

## 概述

系统已重新设计，将链（Chain）和币种（Token）分开管理，提供更灵活的配置方式。

### 核心概念

1. **Chain（链）**: 区块链网络（如 TRON、Ethereum、BNB Chain 等）
2. **Token（币种）**: 加密货币（如 USDT、USDC、TRX、ETH 等）
3. **TokenChainSupport（币种链支持）**: 币种和链的多对多关系，定义某个币种在特定链上的配置

### 设计理念

- **链和币种独立管理**: 每个都有自己的配置（简称、全称、备注等）
- **先选币种，再选链**: 用户选择要充值的币种后，系统显示该币种支持的所有链
- **灵活配置**: 每个币种-链组合可以有独立的合约地址、最小金额、手续费等配置

## 预设数据

### 支持的链

| 代码 | 名称 | 全称 | 原生代币 | 确认块数 |
|------|------|------|----------|----------|
| TRON | TRON | TRON Blockchain Network | TRX | 19 |
| ETHEREUM | Ethereum | Ethereum Blockchain Network | ETH | 12 |
| BNB_CHAIN | BNB Chain | BNB Smart Chain (BSC) | BNB | 15 |
| SOLANA | Solana | Solana Blockchain Network | SOL | 1 |
| TON | The Open Network | The Open Network (TON) | TON | 1 |

### 支持的币种

| 代码 | 符号 | 名称 | 全称 | 是否稳定币 | 小数位 |
|------|------|------|------|-----------|--------|
| USDT | USDT | Tether USD | Tether USD Stablecoin | ✓ | 6 |
| USDC | USDC | USD Coin | USD Coin Stablecoin | ✓ | 6 |
| TRX | TRX | TRON | TRON Native Token | ✗ | 6 |
| SOL | SOL | Solana | Solana Native Token | ✗ | 9 |
| ETH | ETH | Ethereum | Ethereum Native Token | ✗ | 18 |
| BNB | BNB | BNB | Binance Coin | ✗ | 18 |
| TON | TON | Toncoin | The Open Network Token | ✗ | 9 |

### 币种链支持关系

#### USDT 支持的链
- TRON (TRC20): `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`
- Ethereum (ERC20): `0xdAC17F958D2ee523a2206206994597C13D831ec7`
- BNB Chain (BEP20): `0x55d398326f99059fF775485246999027B3197955`
- Solana (SPL): `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB`
- TON: `EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs`

#### USDC 支持的链
- TRON (TRC20): `TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8`
- Ethereum (ERC20): `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- BNB Chain (BEP20): `0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d`
- Solana (SPL): `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`
- TON: `EQC_1YoM8RBixN95lz7odcF3Vrkc_N8Ne7gQi7Abtlet_Efi`

#### 原生代币
- TRX → TRON (原生)
- SOL → Solana (原生)
- ETH → Ethereum (原生)
- BNB → BNB Chain (原生)
- TON → The Open Network (原生)

## 数据库迁移

### 1. 运行迁移创建表结构

```bash
cd /Users/djanbo/www/akx/akx_service

# 运行迁移创建 chains, tokens, token_chain_supports 表
uv run alembic upgrade head
```

### 2. 初始化预设数据

```bash
# 运行初始化脚本填充预设的链和币种数据
uv run python -m src.scripts.init_chains_tokens
```

输出示例：
```
Starting chains and tokens initialization...

1. Creating chains...
   + Created chain: TRON (TRON)
   + Created chain: Ethereum (ETHEREUM)
   + Created chain: BNB Chain (BNB_CHAIN)
   + Created chain: Solana (SOLANA)
   + Created chain: The Open Network (TON)
✓ Chains initialized: 5 chains

2. Creating tokens...
   + Created token: Tether USD (USDT)
   + Created token: USD Coin (USDC)
   + Created token: TRON (TRX)
   + Created token: Solana (SOL)
   + Created token: Ethereum (ETH)
   + Created token: BNB (BNB)
   + Created token: Toncoin (TON)
✓ Tokens initialized: 7 tokens

3. Creating token-chain support mappings...
   + Created support: USDT on TRON
   + Created support: USDT on ETHEREUM
   ...
✓ Token-chain supports initialized: 15 mappings

============================================================
✓ All chains and tokens initialized successfully!
============================================================
```

## API 使用

### 获取所有币种

```bash
GET /api/tokens?is_enabled=true
```

响应：
```json
[
  {
    "id": 1,
    "code": "USDT",
    "symbol": "USDT",
    "name": "Tether USD",
    "full_name": "Tether USD Stablecoin",
    "is_enabled": true,
    "is_stablecoin": true,
    "decimals": 6,
    ...
  }
]
```

### 获取币种支持的链（推荐方式）

这是前端充值流程的主要接口：用户先选币种，再选链。

```bash
GET /api/tokens/{token_id}/with-chains
```

响应：
```json
{
  "id": 1,
  "code": "USDT",
  "name": "Tether USD",
  "supported_chains": [
    {
      "chain_id": 1,
      "chain_code": "TRON",
      "chain_name": "TRON",
      "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
      "decimals": 6,
      "is_native": false,
      "min_deposit": "1.0",
      "min_withdrawal": "10.0",
      "withdrawal_fee": "1.0",
      "confirmation_blocks": 19
    },
    {
      "chain_id": 2,
      "chain_code": "ETHEREUM",
      "chain_name": "Ethereum",
      ...
    }
  ]
}
```

### 管理链（管理员）

```bash
# 列出所有链
GET /api/chains

# 获取链详情
GET /api/chains/{chain_id}

# 创建新链（需要 super_admin 权限）
POST /api/chains
{
  "code": "POLYGON",
  "name": "Polygon",
  "full_name": "Polygon Network",
  "native_token": "MATIC",
  "confirmation_blocks": 128
}

# 更新链配置
PATCH /api/chains/{chain_id}
{
  "is_enabled": false
}
```

### 管理币种（管理员）

```bash
# 列出所有币种
GET /api/tokens

# 创建新币种
POST /api/tokens
{
  "code": "USDC",
  "symbol": "USDC",
  "name": "USD Coin",
  "full_name": "USD Coin Stablecoin",
  "decimals": 6,
  "is_stablecoin": true
}
```

### 管理币种-链支持关系（管理员）

```bash
# 为币种添加链支持
POST /api/token-chain-supports
{
  "token_id": 1,
  "chain_id": 3,
  "contract_address": "0x...",
  "min_deposit": "1.0",
  "min_withdrawal": "10.0",
  "withdrawal_fee": "0.5"
}

# 更新配置
PATCH /api/token-chain-supports/{support_id}
{
  "min_withdrawal": "20.0",
  "withdrawal_fee": "1.0"
}

# 禁用某条链上的币种
PATCH /api/token-chain-supports/{support_id}
{
  "is_enabled": false
}
```

## 充值流程示例

### 前端实现

1. **用户选择币种**
   ```
   显示：USDT, USDC, TRX, ETH, SOL, BNB, TON
   用户点击：USDT
   ```

2. **获取该币种支持的链**
   ```
   GET /api/tokens/1/with-chains
   
   返回 USDT 支持的链：
   - TRON (费用最低 1 USDT)
   - Ethereum (费用 5 USDT)
   - BNB Chain (费用 0.5 USDT)
   - Solana (费用 0.1 USDT)
   - TON (费用 0.5 USDT)
   ```

3. **用户选择链**
   ```
   用户选择：TRON (因为手续费低且熟悉)
   ```

4. **创建充值订单**
   ```
   POST /api/orders
   {
     "token_id": 1,      // USDT
     "chain_id": 1,      // TRON
     "amount": "100.00"
   }
   ```

5. **后端生成充值地址**
   ```
   - 查询 token_id=1, chain_id=1 的 TokenChainSupport
   - 获取合约地址: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
   - 分配 TRON 链上的充值钱包
   - 返回充值地址给用户
   ```

## 数据模型变更

### 旧系统（已废弃）

```python
# 枚举方式 - 不灵活
class Chain(str, Enum):
    TRON = "tron"
    ETHEREUM = "ethereum"

class Token(str, Enum):
    USDT = "usdt"
    USDC = "usdc"
```

### 新系统

```python
# 数据库表 - 灵活可配置
class Chain(SQLModel, table=True):
    code: str
    name: str
    full_name: str
    rpc_url: str
    confirmation_blocks: int
    ...

class Token(SQLModel, table=True):
    code: str
    symbol: str
    name: str
    decimals: int
    is_stablecoin: bool
    ...

class TokenChainSupport(SQLModel, table=True):
    token_id: int
    chain_id: int
    contract_address: str
    min_deposit: str
    withdrawal_fee: str
    ...
```

### Wallet 模型更新

```python
# 旧
class Wallet(SQLModel, table=True):
    chain: Chain  # 枚举

# 新
class Wallet(SQLModel, table=True):
    chain_id: int  # 外键到 chains 表
    token_id: int  # 外键到 tokens 表（可选）
```

## 向后兼容

为了平滑迁移，保留了旧的枚举和函数（标记为 DEPRECATED）：

```python
from src.models.wallet import (
    ChainEnum,  # DEPRECATED - 使用 Chain 表代替
    TokenEnum,  # DEPRECATED - 使用 Token 表代替
    get_token_contract_deprecated,  # DEPRECATED
)
```

**建议**：所有新代码使用新的 Chain、Token、TokenChainSupport 表。

## 注意事项

1. **数据迁移**: 如果已有 wallets 数据，需要手动迁移旧的 chain 枚举字段到 chain_id
2. **权限控制**: 链和币种管理接口应限制为 super_admin 角色
3. **合约地址验证**: 创建 TokenChainSupport 时应验证合约地址格式
4. **币种精度**: 不同链上同一币种可能有不同的小数位（使用 TokenChainSupport.decimals 覆盖）

## 未来扩展

可以轻松添加新链和币种，例如：

- **Arbitrum** (Layer 2)
- **Optimism** (Layer 2)
- **Avalanche**
- **Aptos**
- 更多 ERC-20 代币 (DAI, BUSD 等)

只需：
1. 在 chains 表添加新链
2. 在 tokens 表添加新币种
3. 在 token_chain_supports 表建立关联
4. 无需修改代码！
