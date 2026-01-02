# Role
你是一位拥有10年以上金融支付系统开发经验的资深后端架构师，精通区块链技术（EVM, TVM, Solana）、密码学安全以及高性能 Python Web 开发。

# Task
请基于 **FastAPI (Python)** 构建一套 **加密货币支付交易系统（Crypto Payment Gateway）** 的后端 API。
该系统需要采用前后端分离架构，专注于提供高安全、高并发的 API 服务。

# 1. Tech Stack & Environment (技术栈与环境)
请严格遵守以下技术选型：

1. **Package Manager**: 使用 **uv** (Astral sh)。
   *原因：用户原定使用 Bun 管理 Python，但考虑到 Python 生态兼容性，uv 是目前最快且体验最接近 Bun 的 Python 现代化管理工具。*
2. **Language**: Python (Latest Stable Version).
3. **Web Framework**: FastAPI (Latest).
4. **ORM**: SQLModel (Latest).
5. **Database**: **MySQL 8.0+** (使用 InnoDB 引擎)。
   *关键点：必须使用异步驱动，推荐 `aiomysql` 或 `asyncmy`。*
6. **Validation**: Pydantic V2.
7. **Documentation**: FastAPI 自带的 Swagger UI (/docs).
8. **Authentication**: 集成 **Clerk** (clerk-sdk-python) 进行身份验证。
9. **Async**: 全程使用 `async/await` 异步编程。

# 2. Architecture & Project Structure (架构设计)
项目采用 **模块化单体 (Modular Monolith)** 架构，针对不同链进行逻辑隔离。
建议的目录结构如下：

/src
  /api              # API 路由 (v1)
    /auth           # 用户同步与权限验证
    /merchant       # 商户接口 (下单, 提现, 查单)
    /admin          # 管理后台接口 (系统设置, 审批)
    /webhook        # 接收区块链节点回调
  /core             # 核心配置, 安全工具(AES加密), 异常处理
  /db               # 数据库连接 (SQLModel + Async MySQL Engine)
  /models           # 数据库模型 (Users, Wallets, Orders, Transactions)
  /schemas          # Pydantic DTO (Request/Response)
  /services         # 业务逻辑层
    /clerk_service  # 用户同步逻辑
    /wallet_service # 钱包生成、私钥存取
    /order_service  # 充值与提现核心逻辑
    /finance_service# 费率计算与流水记录
  /chains           # 链上交互层 (工厂模式)
    /base.py        # ChainInterface 抽象类
    /tron.py        # TRON 实现 (tronpy)
    /ethereum.py    # ETH 实现 (web3.py)
    /solana.py      # SOL 实现 (solana-py)
  /workers          # 后台任务 (扫块 Monitor, 资金归集 Sweeper)

# 3. Core Features & Business Logic (核心功能)

## 3.1 用户与权限 (Auth & Roles)
- **Clerk 集成**: 使用 Clerk 验证 JWT，但必须编写中间件将 Clerk User 同步到本地 MySQL `users` 表。
- **角色管理**:
  1. **Super Admin**: 系统配置、费率调整、商户管理。
  2. **Merchant**: 充提业务、API Key 管理、查看报表。
  3. **Support**: 客服，仅拥有查询和只读权限。
- **安全验证**: 敏感操作（提现、导出私钥、修改安全设置）强制要求 Google Auth (TOTP) 验证。

## 3.2 钱包管理 (Wallet Management) - 高安全级
- **生成方式**:
  1. **自动生成**: 系统为商户分配专属充值地址。
  2. **手动导入**: 商户提供地址和私钥（需校验有效性）。
- **私钥存储 (核心安全需求)**:
  - 数据库中**严禁明文存储私钥**。
  - 入库前：使用 AES-256-GCM 进行加密。
  - 出库时：在内存中解密使用，用完即焚。
  - 密钥管理：加密用的 Key 从环境变量读取，不写入代码或数据库。
- **支持链与币种**:
  - 架构设计需支持多链扩展。
  - 首期支持：TRON (USDT-TRC20), ETHEREUM (USDT-ERC20), SOLANA (USDT-SPL)。

## 3.3 充值订单 (Deposit)
- **流程**: 商户获取地址 -> 客户转账 -> 系统通过链上查询确认 -> 回调商户 Webhook。
- **验证**: 必须根据不同链设定确认数（例如 TRON 需 19 个确认）。
- **资金归集 (Sweeping)**:
  - 系统需检测收款钱包是否有 Gas 费（TRX/ETH）。
  - 如无 Gas，系统自动打入手续费，再将 USDT 转入系统冷钱包。

## 3.4 提现订单 (Withdrawal)
- **流程**: 商户发起 -> 系统风控检查（余额、谷歌验证码） -> 广播交易 -> 轮询状态。
- **状态管理**: 提现是异步过程，需处理 PENDING -> PROCESSING -> SUCCESS/FAILED 状态流转。

## 3.5 流水与费率 (Ledger & Fees)
- **计价单位**: 全局使用 USDT。
- **费率模型**: `(金额 * 百分比) + 固定单笔费`。
- **商户账户**: 商户拥有“资金余额”和“手续费余额”。
- **流水记录**: 任何资金变动必须写入流水表，包含 `pre_balance`, `change_amount`, `post_balance`。

## 3.6 首页 Dashboard
- 提供 API 返回：
  - 充值/提现成功率图表数据。
  - 累计流水统计。
  - 待处理订单数。

# 4. Database Schema Design (MySQL 适配)
使用 SQLModel 定义模型，注意 MySQL 特性：
1. **String Length**: 所有的 `str` 字段若作为索引（如 address, tx_hash, email, order_no），**必须**在 `Field` 中指定 `max_length` (例如 255)，否则 MySQL 建表会失败。
2. **Decimal**: 金额字段必须使用 `DECIMAL(32, 8)`，严禁使用 Float。
3. **JSON**: 链上元数据信息使用 MySQL JSON 类型。

主要表结构建议：
- `users`: id, clerk_id, email, role, google_secret, is_active.
- `wallets`: id, user_id, chain, address, encrypted_private_key, type (DEPOSIT/GAS/COLD).
- `orders`: id, order_no, merchant_ref, type, amount, fee, status, tx_hash, created_at.
- `transactions`: id, wallet_id, amount, direction, balance_snapshot, type (FEE/TRANSFER).

# 5. Deliverables (交付要求)
请按顺序提供以下代码/文件：
1. **项目文件结构说明**。
2. **pyproject.toml**: 包含 fastapi, sqlmodel, aiomysql, clerk-sdk-python, cryptography, tronpy 等依赖。
3. **core/security.py**: 实现 AES 加密和解密工具。
4. **db/engine.py**: 配置异步 MySQL Engine。
5. **models/all_models.py**: 包含 User, Wallet, Order 的 SQLModel 定义（注意 max_length）。
6. **chains/tron.py**: TRON 链的查询余额与转账逻辑实现（展示如何处理精度）。
7. **api/merchant_endpoints.py**: 包含商户“申请充值地址”和“提现”的接口实现。

请确保代码逻辑严谨，特别是在处理金额（Decimal）和私钥加密的部分。