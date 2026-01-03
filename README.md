# AKX Backend API

区块链资产配置管理系统后端 API，提供链、币种、钱包的配置和管理功能。

## 功能概述

- ✅ **用户认证**：基于 Clerk 的 JWT 认证，用户自动同步到本地数据库
- ✅ **链管理**：支持多链配置（TRON、Ethereum、Solana 等），包含 RPC、区块浏览器、确认块数等信息
- ✅ **币种管理**：配置支持的代币（USDT、USDC 等），包含精度、图标、稳定币标识等
- ✅ **链币种关系**：通过中间表管理币种在不同链上的支持情况，包含合约地址和手续费配置
- ✅ **钱包管理**：查询和管理钱包配置，支持按链、用户等多维度筛选

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| 语言 | Python 3.12+ |
| 框架 | FastAPI |
| ORM | SQLModel |
| 数据库 | MySQL 8.0+ (aiomysql 异步驱动) |
| 迁移 | Alembic |
| 认证 | Clerk Backend API |
| 包管理 | uv (Astral) |

## 数据模型

系统包含 5 张核心表：

```
users                      # 用户表（Clerk 同步）
├── id (主键)
├── clerk_id (唯一)
├── email
├── role (SUPER_ADMIN/MERCHANT/GUEST)
└── is_active

chains                     # 区块链网络配置
├── id (主键)
├── code (TRON/ETH/SOL...)
├── name, full_name
├── rpc_url, explorer_url
├── confirmation_blocks
└── is_enabled

tokens                     # 代币配置
├── id (主键)
├── code, symbol (USDT/USDC...)
├── name, full_name
├── decimals
└── is_enabled

token_chain_supports       # 币种-链支持关系（多对多）
├── id (主键)
├── token_id (外键 → tokens)
├── chain_id (外键 → chains)
├── contract_address
├── deposit_fee, withdraw_fee
└── is_enabled

wallets                    # 钱包配置
├── id (主键)
├── user_id (外键 → users)
├── chain_id (外键 → chains)
├── token_id (外键 → tokens)
├── address
└── wallet_type
```

## 快速开始

### 环境要求

- Python 3.12+
- MySQL 8.0+
- [uv](https://docs.astral.sh/uv/) (Python 包管理器)

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd akx_service

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填写数据库和 Clerk 配置
```

### 配置环境变量

编辑 `.env` 文件：

```bash
# 数据库
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/akx_db

# Clerk 认证
CLERK_SECRET_KEY=sk_test_xxx
CLERK_PUBLISHABLE_KEY=pk_test_xxx
```

### 初始化数据库

```bash
# 应用数据库迁移
uv run alembic upgrade head

# 初始化预设的链和币种数据（可选）
uv run python -m src.scripts.init_chains_tokens
```

初始化脚本会创建：
- 5 条链：TRON, Ethereum, Solana, Polygon, BSC
- 7 种币：USDT, USDC, DAI, BUSD, WBTC, WETH, SOL
- 15 条支持关系（如 USDT-TRC20, USDT-ERC20 等）

### 运行

```bash
# 开发模式（热重载）
uv run fastapi dev src/main.py

# 生产模式
uv run fastapi run src/main.py
```

访问 API 文档：http://localhost:8000/docs

## API 端点

### 认证 (`/api/auth`)

- `GET /auth/me` - 获取当前用户信息

### 钱包 (`/api/wallets`)

- `GET /wallets` - 查询钱包列表（支持分页、筛选）

### 链管理 (`/api/chains`)

- `GET /chains` - 获取所有链配置
- `GET /chains/{id}` - 获取指定链详情
- `POST /chains` - 创建新链（管理员）
- `PATCH /chains/{id}` - 更新链配置（管理员）
- `DELETE /chains/{id}` - 删除链（管理员）

### 币种管理 (`/api/tokens`)

- `GET /tokens` - 获取所有币种
- `GET /tokens/{id}` - 获取指定币种详情
- `GET /tokens/{id}/with-chains` - 获取币种及其支持的所有链
- `POST /tokens` - 创建新币种（管理员）
- `PATCH /tokens/{id}` - 更新币种配置（管理员）
- `DELETE /tokens/{id}` - 删除币种（管理员）

### 币种-链支持关系 (`/api/token-chain-supports`)

- `GET /token-chain-supports` - 获取所有支持关系
- `GET /token-chain-supports/{id}` - 获取指定关系详情
- `POST /token-chain-supports` - 创建支持关系（管理员）
- `PATCH /token-chain-supports/{id}` - 更新关系配置（管理员）
- `DELETE /token-chain-supports/{id}` - 删除支持关系（管理员）

## 项目结构

```
src/
├── main.py                    # FastAPI 应用入口
├── api/                       # API 路由
│   ├── auth.py               # 认证相关
│   ├── wallets.py            # 钱包管理
│   └── chains_tokens.py      # 链和币种管理（18个端点）
├── models/                    # SQLModel 数据模型
│   ├── user.py               # 用户模型
│   ├── wallet.py             # 钱包模型
│   ├── chain.py              # 链模型
│   └── token.py              # 币种和关系模型
├── schemas/                   # Pydantic DTOs
│   └── chain_token.py        # 链/币种请求响应模型
├── core/                      # 核心配置
│   ├── config.py             # Pydantic Settings
│   ├── security.py           # 安全工具
│   └── exceptions.py         # 自定义异常
├── db/                        # 数据库
│   └── engine.py             # 异步 MySQL 引擎
├── scripts/                   # 工具脚本
│   └── init_chains_tokens.py # 初始化预设数据
└── services/                  # 业务逻辑层（保留目录）

alembic/
└── versions/
    └── de10130405a2_*.py     # 初始数据库迁移
```

## 开发命令

```bash
# 代码格式化
uv run ruff format src/

# 代码检查
uv run ruff check src/ --fix

# 类型检查
uv run mypy src/
```

## 数据库迁移

```bash
# 查看当前版本
uv run alembic current

# 查看迁移历史
uv run alembic history

# 生成新迁移（修改模型后）
uv run alembic revision --autogenerate -m "描述变更"

# 应用迁移
uv run alembic upgrade head

# 回滚上一个迁移
uv run alembic downgrade -1

# 回滚到指定版本
uv run alembic downgrade <revision_id>
```

## 角色权限

系统定义了三种用户角色：

- **SUPER_ADMIN**：超级管理员，拥有所有权限
- **MERCHANT**：商户用户，可查看自己的钱包和配置
- **GUEST**：访客，仅查看权限

大部分配置管理接口（创建/修改/删除链、币种）需要 `SUPER_ADMIN` 权限。

## 认证流程

1. 前端使用 Clerk 完成用户登录，获取 JWT token
2. 前端在请求头中携带 `Authorization: Bearer <token>`
3. 后端验证 Clerk JWT，提取 `clerk_id`
4. 在本地 `users` 表查找或创建用户记录
5. 返回用户信息供业务逻辑使用

## 链和币种配置流程

### 典型使用场景

**场景 1：添加新链**
```bash
POST /api/chains
{
  "code": "POLYGON",
  "name": "Polygon",
  "full_name": "Polygon (Matic Network)",
  "rpc_url": "https://polygon-rpc.com",
  "explorer_url": "https://polygonscan.com",
  "confirmation_blocks": 128,
  "is_enabled": true
}
```

**场景 2：添加新币种**
```bash
POST /api/tokens
{
  "code": "SHIB",
  "symbol": "SHIB",
  "name": "Shiba Inu",
  "decimals": 18,
  "is_enabled": true
}
```

**场景 3：配置币种在某条链上的支持**
```bash
POST /api/token-chain-supports
{
  "token_id": 8,  # SHIB
  "chain_id": 2,  # Ethereum
  "contract_address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",
  "deposit_fee": "0.00",
  "withdraw_fee": "100000",  # 0.1 SHIB
  "is_enabled": true
}
```

**场景 4：前端币种选择流程**
```bash
# 1. 用户选择币种
GET /api/tokens/{token_id}/with-chains

# 返回：
{
  "id": 1,
  "code": "USDT",
  "symbol": "USDT",
  "name": "Tether USD",
  "supported_chains": [
    {
      "chain_id": 1,
      "chain_code": "TRON",
      "chain_name": "TRON",
      "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
      "deposit_fee": "0.00",
      "withdraw_fee": "1.00"
    },
    {
      "chain_id": 2,
      "chain_code": "ETH",
      "chain_name": "Ethereum",
      "contract_address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
      "deposit_fee": "0.00",
      "withdraw_fee": "5.00"
    }
  ]
}

# 2. 用户从 supported_chains 中选择具体链
```

## 常见问题

**Q: 如何添加自定义链？**

A: 使用 `POST /api/chains` 创建，需要 SUPER_ADMIN 权限。

**Q: 如何让某个币种支持新链？**

A: 使用 `POST /api/token-chain-supports` 创建关联，填写合约地址和手续费。

**Q: 初始化脚本可以重复运行吗？**

A: 不建议。脚本会检查 `code` 唯一性，重复运行会报错。如需重置，请清空相关表。

**Q: 如何修改手续费？**

A: 使用 `PATCH /api/token-chain-supports/{id}` 更新 `deposit_fee` 和 `withdraw_fee`。

## 许可证

MIT
