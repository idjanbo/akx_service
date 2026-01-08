# 用户充值系统 (Recharge System)

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           用户充值系统架构                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐               │
│  │   前端页面     │───▶│   后端 API    │───▶│   数据库      │               │
│  │ (在线充值)     │    │  /recharges/* │    │  MySQL        │               │
│  └───────────────┘    └───────────────┘    └───────────────┘               │
│                              │                     │                        │
│                              ▼                     │                        │
│                       ┌───────────────┐            │                        │
│                       │RechargeService│◀───────────┘                        │
│                       │ 充值业务逻辑   │                                     │
│                       └───────────────┘                                      │
│                              │                                              │
│           ┌──────────────────┼──────────────────┐                          │
│           ▼                  ▼                  ▼                          │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐              │
│  │   地址管理       │ │   订单管理      │ │   到账处理       │              │
│  │ - 实时生成地址   │ │ - 创建订单      │ │ - 检测交易       │              │
│  │ - 分配给用户     │ │ - 状态更新      │ │ - 确认数检查     │              │
│  │                 │ │ - 过期处理      │ │ - 入账余额       │              │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          链上监控 & 归集                              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                       │   │
│  │  ┌───────────────┐      ┌───────────────┐      ┌───────────────┐    │   │
│  │  │  TronService  │      │ CollectService │      │   热钱包       │    │   │
│  │  │  链上交互      │──────▶│  归集服务      │──────▶│  集中管理      │    │   │
│  │  │  - 余额查询    │      │  - 扫描地址    │      │               │    │   │
│  │  │  - 交易监控    │      │  - 创建任务    │      │               │    │   │
│  │  │  - 转账执行    │      │  - 执行转账    │      │               │    │   │
│  │  └───────────────┘      └───────────────┘      └───────────────┘    │   │
│  │                                                                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 数据库模型

### 1. RechargeAddress (充值地址)
```sql
CREATE TABLE recharge_addresses (
    id INT PRIMARY KEY,
    wallet_id INT NOT NULL,           -- 关联钱包
    chain_id INT NOT NULL,            -- 区块链
    token_id INT NOT NULL,            -- 代币
    user_id INT NULL,                 -- 分配给的用户
    status ENUM('available', 'assigned', 'locked', 'disabled'),
    total_recharged DECIMAL(32,8),    -- 累计充值
    last_recharge_at DATETIME,
    assigned_at DATETIME
);
```

### 2. RechargeOrder (充值订单)
```sql
CREATE TABLE recharge_orders (
    id INT PRIMARY KEY,
    order_no VARCHAR(32) UNIQUE,
    user_id INT NOT NULL,
    recharge_address_id INT NOT NULL,
    expected_amount DECIMAL(32,8),     -- 期望金额
    actual_amount DECIMAL(32,8),       -- 实际到账
    status ENUM('pending', 'detected', 'confirming', 'success', 'expired', 'failed'),
    tx_hash VARCHAR(128),
    confirmations INT DEFAULT 0,
    required_confirmations INT DEFAULT 19,  -- TRON 需要 19 确认
    expires_at DATETIME
);
```

### 3. CollectTask (归集任务)
```sql
CREATE TABLE collect_tasks (
    id INT PRIMARY KEY,
    recharge_address_id INT NOT NULL,  -- 源地址
    hot_wallet_id INT NOT NULL,        -- 目标热钱包
    chain_id INT NOT NULL,
    token_id INT NOT NULL,
    amount DECIMAL(32,8),
    status ENUM('pending', 'processing', 'success', 'failed', 'skipped'),
    tx_hash VARCHAR(128),
    gas_used DECIMAL(32,8),
    error_message VARCHAR(500),
    retry_count INT DEFAULT 0
);
```

## API 端点

### 用户端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/recharges/address` | 获取充值地址（自动分配） |
| POST | `/api/recharges/orders` | 创建充值订单 |
| GET | `/api/recharges/orders` | 查询充值订单列表 |
| GET | `/api/recharges/orders/{order_no}` | 查询订单详情 |

### 管理员端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/recharges/admin/orders` | 所有订单列表 |
| POST | `/api/recharges/admin/expire-orders` | 过期订单处理 |
| GET | `/api/recharges/admin/collect/tasks` | 归集任务列表 |
| POST | `/api/recharges/admin/collect/scan` | 扫描创建归集任务 |
| POST | `/api/recharges/admin/collect/execute` | 执行归集 |
| GET | `/api/recharges/admin/collect/stats` | 归集统计 |

## 使用流程

### 1. 用户充值流程
1. 用户访问在线充值页面
2. 选择币种和网络（USDT-TRON）
3. 系统实时生成专属充值地址（首次）或返回已有地址
4. 用户向该地址转账
5. 系统监控链上交易
6. 检测到转账后，等待 19 个确认
7. 确认完成后，自动入账用户余额

### 2. 启动链上监控
```bash
# 后台运行监控脚本
uv run python -m src.scripts.recharge_monitor
```

### 3. 资金归集
```bash
# 扫描并创建归集任务
uv run python -m src.scripts.collect_funds --action scan --hot-wallet-id 1

# 预览归集（不实际执行）
uv run python -m src.scripts.collect_funds --action execute --dry-run

# 执行归集
uv run python -m src.scripts.collect_funds --action execute

# 查看统计
uv run python -m src.scripts.collect_funds --action stats
```

## 归集策略

### 触发条件
- 地址余额 ≥ 10 USDT
- 无进行中的归集任务

### 优化策略
1. **TRON 能量机制**: 热钱包质押 TRX 获取能量，子地址转账消耗热钱包能量
2. **批量执行**: 每次最多执行 10 个归集任务
3. **定时执行**: 建议在 Gas 低谷期（凌晨）执行
4. **阈值控制**: 避免小额频繁归集

### 成本估算 (TRON)
- 每笔 TRC20 转账约需 65,000 能量
- 热钱包质押 1,000 TRX ≈ 获得 ~28,000 能量/天
- 推荐质押 10,000+ TRX 确保足够能量

## 文件结构

```
src/
├── models/
│   └── recharge.py         # 数据模型（RechargeAddress, RechargeOrder, CollectTask）
├── services/
│   ├── recharge_service.py # 充值业务逻辑
│   ├── collect_service.py  # 归集业务逻辑
│   └── tron_service.py     # TRON 链交互
├── api/
│   └── recharges.py        # API 端点
└── scripts/
    ├── recharge_monitor.py    # 链上监控
    └── collect_funds.py       # 归集执行
```

## 安全注意事项

1. **私钥安全**: 所有私钥使用 AES-256-GCM 加密存储
2. **热钱包限额**: 热钱包设置每日转出限额
3. **监控告警**: 异常大额充值自动告警
4. **地址复用**: 用户地址永久分配，不回收（防止混淆）
