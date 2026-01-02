# AKX Crypto Payment Gateway

加密货币支付网关后端 API，支持多链交易（TRON、Ethereum、Solana），以 USDT 作为主要结算货币。

## 快速开始

### 环境要求

- Python 3.12+
- MySQL 8.0+
- [uv](https://docs.astral.sh/uv/) (Python 包管理器)
- pkg-config (macOS: `brew install pkg-config`)

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd akx_service

# 安装依赖
uv sync

# 复制环境变量模板
cp .env.example .env
```

### 配置环境变量

编辑 `.env` 文件：

```bash
# 数据库
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/akx_db

# AES 加密密钥 (用于私钥加密存储)
# 生成方式: uv run python -c "from src.core.security import generate_aes_key; print(generate_aes_key())"
AES_ENCRYPTION_KEY=<your-base64-key>

# Clerk 认证
CLERK_SECRET_KEY=sk_test_xxx
CLERK_PUBLISHABLE_KEY=pk_test_xxx

# TRON (主链)
TRON_API_KEY=<your-trongrid-api-key>
TRON_NETWORK=mainnet  # 或 shasta/nile 测试网
```

### 运行

```bash
# 初始化数据库 (首次运行)
uv run alembic upgrade head

# 开发模式 (热重载)
uv run fastapi dev src/main.py

# 生产模式
uv run fastapi run src/main.py
```

访问 API 文档: http://localhost:8000/docs

## 项目结构

```
src/
├── main.py              # FastAPI 应用入口
├── core/
│   ├── config.py        # 配置管理 (Pydantic Settings)
│   ├── security.py      # AES-256-GCM 加密工具
│   └── exceptions.py    # 自定义异常
├── db/
│   └── engine.py        # 异步 MySQL 引擎
├── models/
│   ├── user.py          # 用户模型 (Clerk 同步)
│   ├── wallet.py        # 钱包模型 (加密私钥)
│   ├── order.py         # 订单模型 (充值/提现)
│   └── transaction.py   # 流水账本
├── chains/
│   ├── base.py          # ChainInterface 抽象类
│   └── tron.py          # TRON 链实现
├── api/                 # API 路由 (待实现)
├── services/            # 业务逻辑层 (待实现)
├── schemas/             # Pydantic DTOs (待实现)
└── workers/             # 后台任务 (待实现)
```

## 开发命令

```bash
# 安装开发依赖
uv sync --dev

# 运行测试
uv run pytest

# 类型检查
uv run mypy src/

# 代码格式化
uv run ruff format src/

# 代码检查
uv run ruff check src/ --fix
```

## 数据库迁移

项目使用 [Alembic](https://alembic.sqlalchemy.org/) 管理数据库迁移。

```bash
# 应用所有迁移 (初始化数据库)
uv run alembic upgrade head

# 查看当前迁移版本
uv run alembic current

# 查看迁移历史
uv run alembic history

# 生成新的迁移 (修改模型后)
uv run alembic revision --autogenerate -m "描述变更"

# 回滚上一个迁移
uv run alembic downgrade -1

# 回滚到指定版本
uv run alembic downgrade <revision_id>

# 离线生成 SQL (不连接数据库)
uv run alembic upgrade head --sql > migration.sql
```

## 核心功能

### 已实现
- [x] 项目骨架与配置
- [x] AES-256-GCM 私钥加密
- [x] 异步 MySQL 数据库引擎
- [x] SQLModel 数据模型 (User, Wallet, Order, Transaction, Webhook, FeeConfig, Merchant)
- [x] TRON 链抽象与实现
- [x] Clerk 认证中间件 (JWT 验证 + 用户同步)
- [x] 商户 API (钱包管理、充值地址、提现、订单查询、余额)
- [x] 管理员 API (用户管理、系统钱包、仪表板统计)
- [x] Webhook 服务 (HMAC 签名、重试机制、投递记录)
- [x] 区块扫描 Worker (监控存款，每链独立进程)
- [x] 资金归集 Sweeper (Gas 补充 + USDT 归集)
- [x] 热钱包提现执行逻辑
- [x] 冻结余额计算 (待处理提现)
- [x] 动态费率配置模型
- [x] Celery 任务队列 (基于 Redis)
- [x] 支付 API (HMAC-SHA256 签名认证)
- [x] 商户密钥管理 (充值密钥 / 提现密钥)

### 待实现
- [ ] Ethereum 链实现完善
- [ ] Solana 链实现完善
- [ ] Google Authenticator (TOTP) 双因素认证

## 运行后台任务

项目使用 [Celery](https://docs.celeryq.dev/) 作为任务队列，基于 Redis。每条链有独立的 Worker 进程。

### 配置 Redis

```bash
# 启动 Redis (Docker)
docker run -d --name redis -p 6379:6379 redis:alpine

# 或安装本地 Redis (macOS)
brew install redis && brew services start redis
```

### 启动 Workers

```bash
# 启动所有 Workers
uv run celery -A src.workers.celery_app worker -l info

# 启动定时任务调度器 (Beat)
uv run celery -A src.workers.celery_app beat -l info

# 按链独立启动 Worker (生产推荐)
uv run celery -A src.workers.celery_app worker -Q tron -l info -c 1 --hostname=tron@%h
uv run celery -A src.workers.celery_app worker -Q ethereum -l info -c 1 --hostname=eth@%h
uv run celery -A src.workers.celery_app worker -Q solana -l info -c 1 --hostname=sol@%h
uv run celery -A src.workers.celery_app worker -Q common -l info -c 2 --hostname=common@%h
```

### 定时任务

| 任务 | 队列 | 间隔 | 描述 |
|-----|------|------|------|
| scan_tron_blocks | tron | 10秒 | 扫描 TRON 区块 |
| scan_ethereum_blocks | ethereum | 15秒 | 扫描 Ethereum 区块 |
| scan_solana_blocks | solana | 5秒 | 扫描 Solana 区块 |
| sweep_funds | common | 5分钟 | 归集资金到冷钱包 |
| retry_webhooks | common | 1分钟 | 重试失败的 Webhook |
| process_withdrawals | common | 30秒 | 处理待执行提现 |

## 支付 API

商户通过 API 密钥 + HMAC-SHA256 签名调用支付接口。

详见 [支付接入文档](docs/PAYMENT_API.md)

## 安全注意事项

⚠️ **私钥安全**
- 私钥使用 AES-256-GCM 加密后存储
- `AES_ENCRYPTION_KEY` 必须从环境变量读取，禁止写入代码
- 私钥解密后仅在内存中使用，用完立即清除

⚠️ **API 密钥安全**
- 商户有两套密钥：`deposit_key` 和 `withdraw_key`
- 密钥用于 HMAC-SHA256 签名验证
- 请妥善保管，不要泄露

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| 框架 | FastAPI |
| ORM | SQLModel + aiomysql |
| 数据库 | MySQL 8.0+ |
| 任务队列 | Celery + Redis |
| 认证 | Clerk / HMAC-SHA256 |
| 加密 | cryptography (AES-256-GCM) |
| 区块链 | tronpy, web3.py, solana-py |

## 文档

- [SPEC.md](SPEC.md) - 详细技术规格文档
- [docs/PAYMENT_API.md](docs/PAYMENT_API.md) - 支付接入文档

## License

MIT
