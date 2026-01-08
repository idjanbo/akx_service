# AKX Crypto Payment Gateway - Copilot Instructions

## Project Overview
A cryptocurrency payment gateway backend API built with FastAPI, supporting multi-chain transactions (TRON, Ethereum, Solana) with USDT as the primary settlement currency.

## Tech Stack
- **Package Manager**: `uv` (Astral) - use `uv add` for dependencies, `uv run` for execution
- **Framework**: FastAPI with full async/await patterns
- **ORM**: SQLModel with async MySQL driver (`aiomysql` or `asyncmy`)
- **Database**: MySQL 8.0+ (InnoDB)
- **Auth**: Clerk SDK for JWT verification, synced to local `users` table
- **Validation**: Pydantic V2

## Development Workflows
```bash
# Install dependencies
uv sync

# Run dev server
uv run fastapi dev src/main.py

# Run production
uv run fastapi run src/main.py

# Add dependencies
uv add <package>
uv add --dev <dev-package>

# Run tests
uv run pytest

# Type checking
uv run mypy src/
```

## Required Environment Variables
```bash
# Database
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/akx_db

# Security (32-byte key, base64 encoded)
AES_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Clerk Authentication
CLERK_SECRET_KEY=sk_live_xxx
CLERK_PUBLISHABLE_KEY=pk_live_xxx

# TRON (Primary Chain)
TRON_API_KEY=<trongrid-api-key>
TRON_NETWORK=mainnet  # or shasta for testnet

# Redis (Task Queue)
REDIS_URL=redis://localhost:6379

# Ethereum (Secondary)
ETH_RPC_URL=https://mainnet.infura.io/v3/xxx

# Solana (Tertiary)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

## Architecture: Modular Monolith with Service Layer

项目采用**三层架构**：API → Service → Model

```
/src
  /api              # API 路由层 - 处理 HTTP 请求/响应，参数验证
  /services         # 业务逻辑层 - 核心业务逻辑，可复用
  /utils            # 工具函数层 - 通用辅助函数
  /models           # 数据模型层 - SQLModel 实体定义
  /schemas          # Pydantic DTOs - 请求/响应数据结构
  /core             # 核心配置 - Config, AES encryption, exceptions
  /db               # 数据库配置 - Async MySQL engine setup
  /scripts          # 独立脚本 - 初始化、数据迁移等
```

### 目录结构详解

```
src/
├── api/                    # API 路由层
│   ├── __init__.py
│   ├── deps.py            # 公共依赖类型别名 (CurrentUser, SuperAdmin, TOTPUser 等)
│   ├── auth.py            # 认证中间件 (Clerk JWT)
│   ├── wallets.py         # 钱包 API 端点
│   ├── orders.py          # 订单 API 端点
│   ├── payment_channels.py # 支付通道 API 端点
│   ├── chains_tokens.py   # 链和代币 API 端点
│   ├── fee_configs.py     # 费率配置 API 端点
│   ├── users.py           # 用户管理 API 端点
│   └── totp.py            # TOTP 验证 API 端点
│
├── services/              # 业务逻辑层
│   ├── __init__.py
│   ├── wallet_service.py      # 钱包业务逻辑
│   ├── channel_service.py     # 支付通道业务逻辑
│   ├── chain_token_service.py # 链和代币业务逻辑
│   ├── fee_config_service.py  # 费率配置业务逻辑
│   └── user_service.py        # 用户管理业务逻辑
│
├── utils/                 # 工具函数层
│   ├── __init__.py
│   ├── crypto.py          # 加密相关工具 (钱包生成、地址验证)
│   ├── pagination.py      # 分页工具
│   └── helpers.py         # 通用辅助函数
│
├── models/                # SQLModel 实体
├── schemas/               # Pydantic DTOs
├── core/                  # 核心配置
├── db/                    # 数据库配置
└── scripts/               # 独立脚本 (init_chains_tokens.py, init_fee_configs.py 等)
```

## 代码分层规范 (重要)

### API 层 (api/*.py)
**职责**：
- HTTP 请求/响应处理
- 参数验证 (Pydantic)
- 错误转换 (ValueError → HTTPException)
- 权限检查依赖注入

**规范**：
```python
# ✅ 正确：API 层只处理 HTTP 相关逻辑
@router.get("/{wallet_id}")
async def get_wallet(
    wallet_id: int,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> WalletResponse:
    result = await service.get_wallet(wallet_id, user)
    if not result:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return WalletResponse(**result)

# ❌ 错误：API 层不应该包含业务逻辑
@router.get("/{wallet_id}")
async def get_wallet(wallet_id: int, db: AsyncSession = Depends(get_db)):
    wallet = await db.get(Wallet, wallet_id)
    # 大量业务逻辑代码...
```

### Service 层 (services/*.py)
**职责**：
- 核心业务逻辑
- 数据库操作
- 跨模型协调
- 返回领域对象或字典

**规范**：
```python
class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_wallet(self, wallet_id: int, user: User) -> dict | None:
        """获取钱包 - 业务逻辑在这里"""
        wallet = await self.db.get(Wallet, wallet_id)
        if not wallet:
            return None
        
        # 权限检查是业务逻辑
        if user.role == UserRole.MERCHANT and wallet.user_id != user.id:
            return None
        
        # 组装返回数据
        return self._wallet_to_dict(wallet)

    async def generate_wallets(self, user: User, chain_id: int, count: int):
        """生成钱包 - 抛出 ValueError 表示业务错误"""
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            raise ValueError(f"Chain {chain_id} not found")
        # ...
```

### Utils 层 (utils/*.py)
**职责**：
- 无状态工具函数
- 不依赖数据库
- 可跨 Service 复用

**规范**：
```python
# utils/crypto.py
def generate_wallet_for_chain(chain_code: str) -> tuple[str, str]:
    """生成钱包地址和私钥 - 纯函数，无副作用"""
    ...

def validate_address_for_chain(chain_code: str, address: str) -> bool:
    """验证地址格式 - 纯函数"""
    ...

# utils/pagination.py
@dataclass
class PaginationParams:
    page: int = 1
    page_size: int = 20

async def paginate_query(db: AsyncSession, query: Select, params: PaginationParams):
    """通用分页函数"""
    ...
```

## Service 依赖注入

在 API 层使用 FastAPI 依赖注入创建 Service 实例：

```python
# api/wallets.py
def get_wallet_service(db: Annotated[AsyncSession, Depends(get_db)]) -> WalletService:
    """创建 WalletService 实例"""
    return WalletService(db)

@router.get("")
async def list_wallets(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[WalletService, Depends(get_wallet_service)],
):
    return await service.list_wallets(user, ...)
```

## API 依赖类型别名 (重要规范)

项目封装了常用的认证/权限依赖为类型别名，位于 `src/api/deps.py`。

### 可用的类型别名

| 类型别名 | 描述 | 使用场景 |
|---------|------|---------|
| `CurrentUser` | 已认证用户 | 普通接口，只需登录 |
| `TOTPUser` | 已绑定 TOTP 的用户 | 敏感操作前置检查 |
| `NonGuestUser` | 非 Guest 角色用户 | 排除游客访问 |
| `SuperAdmin` | 超级管理员 | 系统配置、用户管理等 |
| `AdminOrSupport` | 管理员或客服 | 订单查询、客服操作 |

### 使用方式

```python
from src.api.deps import CurrentUser, SuperAdmin, TOTPUser

# ✅ 正确：使用类型别名（简洁）
@router.get("/wallets")
async def list_wallets(user: CurrentUser): ...

@router.delete("/users/{id}")
async def delete_user(user: SuperAdmin): ...

# ❌ 错误：不要直接写 Annotated（冗长且不统一）
@router.get("/wallets")
async def list_wallets(user: Annotated[User, Depends(get_current_user)]): ...
```

### TOTP 验证装饰器 `@totp_required` (推荐)

对于需要 TOTP 验证的敏感操作，使用 `@totp_required` 装饰器：

```python
from src.api.deps import TOTPUser, totp_required

@router.post("/sensitive-action")
@totp_required  # 装饰器自动从 data.totp_code 获取验证码并验证
async def sensitive_action(
    user: TOTPUser,  # 确保用户已绑定 TOTP
    data: RequestWithTOTP,  # 请求体必须包含 totp_code 字段
):
    # 已通过 TOTP 验证，直接写业务逻辑
    ...
```

**装饰器工作原理**：
- 自动从 `kwargs["user"]` 获取用户
- 自动从 `kwargs["data"].totp_code` 获取验证码
- 验证失败直接抛出 `HTTPException(400)`

**请求体 Schema 示例**：
```python
class ForceCompleteRequest(BaseModel):
    remark: str = Field(min_length=1, max_length=500)
    totp_code: str = Field(min_length=6, max_length=6)  # 必须包含此字段
```

**完整示例**：
```python
from src.api.deps import TOTPUser, totp_required

@router.post("/{order_id}/force-complete")
@totp_required
async def force_complete(
    order_id: int,
    data: ForceCompleteRequest,
    user: TOTPUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderActionResponse:
    """强制补单 - 需要 TOTP 验证。"""
    result = await service.force_complete(user, order_id, data)
    return OrderActionResponse(**result)
```

### 权限保护规则

| 操作类型 | 所需权限 |
|---------|---------|
| 查询列表/详情 | `CurrentUser` |
| 创建/更新/删除配置 | `SuperAdmin` |
| 敏感操作（强制补单、导出私钥） | `TOTPUser` + `@totp_required` |
| 用户管理 | `SuperAdmin` |
| 订单查询 | `CurrentUser`（Service 层过滤数据） |

## Critical Patterns

### Database Fields (MySQL-specific)
- **All indexed strings** MUST have `max_length` in Field (e.g., `Field(max_length=255)`)
- **Money fields** MUST use `DECIMAL(32, 8)` - NEVER float
- Use MySQL JSON type for chain metadata

### Private Key Security
- **NEVER** store plaintext private keys
- Encrypt with AES-256-GCM before database storage
- Decrypt in memory only when needed, clear immediately after use
- Encryption key MUST come from environment variable

### Payment API Authentication
- Merchants have two keys: `deposit_key` and `withdraw_key`
- All payment API requests signed with HMAC-SHA256
- Signature: `HMAC-SHA256(message, key)`
- Request timestamp must be within 5 minutes

### Blockchain Integration (TRON First)
- TRON requires 19 confirmations for finality
- USDT-TRC20 contract: `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` (mainnet)
- **TODO**: 实现 `/chains/` 区块链抽象层 (base.py, tron.py)

### Order State Machine
Withdrawal states: `PENDING -> PROCESSING -> SUCCESS/FAILED`
- All state transitions must be logged
- Ledger entries require: `pre_balance`, `change_amount`, `post_balance`

### Fee Calculation
Formula: `(amount * percentage) + fixed_fee`
- Global pricing in USDT
- Merchants have separate "balance" and "fee balance" accounts

## Role-Based Access
1. **Super Admin**: System config, fee rates, merchant management
2. **Merchant**: Deposits/withdrawals, API keys, reports
3. **Support**: Read-only queries

Sensitive operations (withdrawals, key export, security settings) require Google Auth (TOTP).

## Database Script Patterns (重要规范)

### 独立脚本中使用数据库 Session
**必须使用 `get_session()` 上下文管理器**，不要尝试使用 FastAPI 的依赖注入方式。

**⚠️ 重要：脚本结束时必须调用 `close_db()` 关闭连接池**，否则会出现 `RuntimeError: Event loop is closed` 错误。

```python
# ✅ 正确：使用 get_session 上下文管理器 + close_db 关闭连接
from src.db.engine import close_db, get_session

async def my_script():
    try:
        async with get_session() as db:
            result = await db.execute(select(Model))
            # 处理数据...
            await db.commit()
    finally:
        # 必须：关闭数据库连接池，避免事件循环关闭时的警告
        await close_db()

if __name__ == "__main__":
    asyncio.run(my_script())
```

```python
# ❌ 错误：不要在脚本中使用 async for（那是 FastAPI 依赖注入的方式）
async for db in get_db():  # 这是 FastAPI 路由用的
    pass

# ❌ 错误：不要尝试导入不存在的函数
from src.db.engine import get_db_for_script  # 不存在！
```

**可用的数据库函数**（定义在 `src/db/engine.py`）：
- `get_session()` - 异步上下文管理器，用于脚本和非 FastAPI 代码
- `get_db()` - FastAPI 依赖注入，仅用于路由处理函数

## Key Libraries
- `tronpy` - TRON interactions (primary)
- `web3.py` - Ethereum interactions
- `solana-py` - Solana interactions
- `cryptography` - AES-256-GCM encryption
- `clerk-backend-api` - Authentication
- `celery` - Task queue (Redis)

## Key Files (update as implemented)

### Core Infrastructure
- `src/core/security.py` - AES encryption utilities
- `src/core/config.py` - Pydantic Settings configuration
- `src/db/engine.py` - Async MySQL engine + session factory

### Services (业务逻辑层)
- `src/services/wallet_service.py` - 钱包业务逻辑 (生成、导入、查询、资产汇总)
- `src/services/channel_service.py` - 支付通道业务逻辑 (CRUD、可用通道查询)
- `src/services/chain_token_service.py` - 链和代币业务逻辑 (CRUD、链代币关联)
- `src/services/fee_config_service.py` - 费率配置业务逻辑 (CRUD、费率计算)
- `src/services/user_service.py` - 用户管理业务逻辑 (CRUD、密钥重置、TOTP)

### Utils (工具函数)
- `src/utils/crypto.py` - 加密工具 (钱包生成、地址验证)
- `src/utils/pagination.py` - 分页工具 (PaginationParams、paginate_query)
- `src/utils/totp.py` - TOTP 工具 (totp_required 装饰器、require_totp_code、verify_totp_code)
- `src/utils/helpers.py` - 通用辅助函数

### API Routes
- `src/api/deps.py` - 公共依赖类型别名 (CurrentUser, SuperAdmin, TOTPUser) + `@totp_required` 装饰器
- `src/api/auth.py` - Clerk JWT verification + user sync
- `src/api/orders.py` - 订单 API 端点 (充值/提现订单、强制补单、重发回调)
- `src/api/wallets.py` - 钱包 API 端点
- `src/api/payment_channels.py` - 支付通道 API 端点
- `src/api/chains_tokens.py` - 链和代币 API 端点
- `src/api/fee_configs.py` - 费率配置 API 端点
- `src/api/users.py` - 用户管理 API 端点
- `src/api/totp.py` - TOTP 验证 API 端点

### Models
- `src/models/` - SQLModel definitions (User, Wallet, Chain, Token, PaymentChannel, FeeConfig)

### Scripts
- `src/scripts/init_chains_tokens.py` - 初始化链和代币数据
- `src/scripts/init_fee_configs.py` - 初始化费率配置
- `src/scripts/update_chain_codes.py` - 更新链代码

### Documentation
- `docs/PAYMENT_API.md` - Payment API documentation
- `docs/CHAIN_TOKEN_SYSTEM.md` - 链和代币系统文档
