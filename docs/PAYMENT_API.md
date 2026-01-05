# AKX Payment Gateway - API 接入文档

## 概述

AKX 支付网关提供加密货币充值和提现服务，支持多链、多币种交易。

### 支持的币种和链

| 币种 (token) | 支持链 (chain) |
|-------------|----------------|
| `USDT` | `tron`, `ethereum`, `solana` |
| `USDC` | `tron`, `ethereum`, `solana` |
| `ETH` | `ethereum` |
| `TRX` | `tron` |
| `SOL` | `solana` |

**重要**：支付方式由 **币种 + 链** 唯一确定。例如 TRON 链上的 USDT 和 Ethereum 链上的 USDT 是不同的支付方式。

## 接入准备

### 1. 获取商户凭证

联系管理员获取以下凭证：

| 参数 | 说明 |
|------|------|
| `merchant_no` | 商户编号，如 `M1234567890123` |
| `deposit_key` | 充值密钥（64位十六进制），用于充值订单和查询 |
| `withdraw_key` | 提现密钥（64位十六进制），用于提现订单和查询 |

### 2. 签名算法

所有 API 请求必须携带 HMAC-SHA256 签名。

#### 签名步骤

1. 按指定顺序拼接参数（不含 `sign` 字段）
2. 使用对应密钥进行 HMAC-SHA256 签名
3. 将签名结果转为小写十六进制字符串

#### Python 示例

```python
import hmac
import hashlib
import time
import secrets

def generate_sign(message: str, secret_key: str) -> str:
    """生成 HMAC-SHA256 签名"""
    return hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

# 示例：充值签名
merchant_no = "M1234567890123"
deposit_key = "your_deposit_key_64_chars..."
timestamp = int(time.time() * 1000)  # 毫秒时间戳
nonce = secrets.token_hex(16)  # 32位随机字符串

# 签名字段顺序：merchant_no + timestamp + nonce + out_trade_no + token + chain + amount + callback_url
message = merchant_no + str(timestamp) + nonce + "ORDER001" + "USDT" + "tron" + "100.00" + "https://example.com/callback"
sign = generate_sign(message, deposit_key)
```

#### Java 示例

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;

public class SignUtil {
    public static String generateSign(String message, String secretKey) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        SecretKeySpec secretKeySpec = new SecretKeySpec(
            secretKey.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
        mac.init(secretKeySpec);
        byte[] hash = mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
        StringBuilder hexString = new StringBuilder();
        for (byte b : hash) {
            String hex = Integer.toHexString(0xff & b);
            if (hex.length() == 1) hexString.append('0');
            hexString.append(hex);
        }
        return hexString.toString();
    }
}
```

---

## API 接口

### 基础 URL

- 测试环境: `https://api-test.akx.com`
- 生产环境: `https://api.akx.com`

### 公共参数

所有请求必须包含以下公共参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `merchant_no` | string | 是 | 商户编号 |
| `timestamp` | int | 是 | 请求时间戳（毫秒），5分钟内有效 |
| `nonce` | string | 是 | 随机字符串（16-32位），防重放攻击 |
| `sign` | string | 是 | HMAC-SHA256 签名 |

---

## 1. 创建充值订单

**POST** `/api/v1/payment/deposit/create`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `out_trade_no` | string | 是 | 外部交易号（最长64字符，商户系统唯一订单号） |
| `token` | string | 是 | 币种：`USDT` / `USDC` / `ETH` / `TRX` / `SOL` |
| `chain` | string | 是 | 区块链网络：`tron` / `ethereum` / `solana` |
| `amount` | string | 是 | 充值金额（最多8位小数） |
| `callback_url` | string | 是 | 回调通知地址 |
| `extra_data` | string | 否 | 附加数据（最长1024字符，回调时原样返回） |

### 签名字段顺序

```
merchant_no + timestamp + nonce + out_trade_no + token + chain + amount + callback_url
```

### 请求示例

```json
{
  "merchant_no": "M1234567890123",
  "timestamp": 1702345678000,
  "nonce": "abc123def456ghij7890",
  "out_trade_no": "ORDER20231212001",
  "token": "USDT",
  "chain": "tron",
  "amount": "100.00",
  "callback_url": "https://yoursite.com/api/callback",
  "extra_data": "{\"user_id\":12345}",
  "sign": "a1b2c3d4e5f6..."
}
```

### 响应示例

```json
{
  "success": true,
  "order_no": "DEP1702345678000ABC12345",
  "out_trade_no": "ORDER20231212001",
  "token": "USDT",
  "chain": "tron",
  "amount": "100.00",
  "wallet_address": "TXyz...abc",
  "expire_time": "2023-12-12T12:30:00Z",
  "created_at": "2023-12-12T12:00:00Z"
}
```

### 重要说明

1. 用户需向 `wallet_address` 转入**精确金额**的指定币种
2. 订单有效期为 30 分钟，超时未支付将自动关闭
3. 系统会自动扫描区块链，检测到转账后触发回调
4. **务必确保转入的币种与订单指定的 `token` 一致**

---

## 2. 创建提现订单

**POST** `/api/v1/payment/withdraw/create`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `out_trade_no` | string | 是 | 外部交易号（最长64字符，商户系统唯一订单号） |
| `token` | string | 是 | 币种：`USDT` / `USDC` / `ETH` / `TRX` / `SOL` |
| `chain` | string | 是 | 区块链网络：`tron` / `ethereum` / `solana` |
| `amount` | string | 是 | 提现金额（最多8位小数） |
| `to_address` | string | 是 | 收款钱包地址 |
| `callback_url` | string | 是 | 回调通知地址 |
| `extra_data` | string | 否 | 附加数据（最长1024字符） |

### 签名字段顺序

```
merchant_no + timestamp + nonce + out_trade_no + token + chain + amount + to_address + callback_url
```

### 请求示例

```json
{
  "merchant_no": "M1234567890123",
  "timestamp": 1702345678000,
  "nonce": "xyz789abc123def456",
  "out_trade_no": "WD20231212001",
  "token": "USDT",
  "chain": "tron",
  "amount": "50.00",
  "to_address": "TLive...xyz",
  "callback_url": "https://yoursite.com/api/callback",
  "extra_data": "{\"user_id\":12345}",
  "sign": "f6e5d4c3b2a1..."
}
```

### 响应示例

```json
{
  "success": true,
  "order_no": "WIT1702345678000DEF67890",
  "out_trade_no": "WD20231212001",
  "token": "USDT",
  "chain": "tron",
  "amount": "50.00",
  "fee": "1.00",
  "net_amount": "49.00",
  "to_address": "TLive...xyz",
  "status": "pending",
  "created_at": "2023-12-12T12:00:00Z"
}
```

### 重要说明

1. 提现会扣除手续费，实际到账金额为 `net_amount`
2. 需确保商户账户有足够的对应币种余额
3. 提现订单状态：`pending` → `processing` → `success` / `failed`

---

## 3. 查询订单（按订单号）

**POST** `/api/v1/payment/order/query`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `order_no` | string | 是 | 系统订单号 |

### 签名字段顺序

```
merchant_no + timestamp + nonce + order_no
```

### 签名密钥

- 查询充值订单：使用 `deposit_key`
- 查询提现订单：使用 `withdraw_key`

### 请求示例

```json
{
  "merchant_no": "M1234567890123",
  "timestamp": 1702345678000,
  "nonce": "query123nonce456",
  "order_no": "DEP1702345678000ABC12345",
  "sign": "1a2b3c4d5e6f..."
}
```

---

## 4. 查询订单（按外部交易号）

**POST** `/api/v1/payment/order/query-by-out-trade-no`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `out_trade_no` | string | 是 | 外部交易号 |
| `order_type` | string | 是 | 订单类型：`deposit` / `withdraw` |

### 签名字段顺序

```
merchant_no + timestamp + nonce + out_trade_no + order_type
```

### 签名密钥

- 充值订单：使用 `deposit_key`
- 提现订单：使用 `withdraw_key`

---

## 5. 订单查询响应

```json
{
  "success": true,
  "order_no": "DEP1702345678000ABC12345",
  "out_trade_no": "ORDER20231212001",
  "order_type": "deposit",
  "token": "USDT",
  "chain": "tron",
  "amount": "100.00",
  "fee": "0.00",
  "net_amount": "100.00",
  "status": "success",
  "wallet_address": "TXyz...abc",
  "tx_hash": "abc123...xyz",
  "confirmations": 19,
  "created_at": "2023-12-12T12:00:00Z",
  "completed_at": "2023-12-12T12:05:00Z",
  "extra_data": "{\"user_id\":12345}"
}
```

---

## 回调通知

### 回调机制

1. 订单完成后，系统会向 `callback_url` 发送 POST 请求
2. 回调失败会自动重试，重试间隔：1分钟、5分钟、15分钟、1小时、6小时
3. 商户需返回 HTTP 200 表示接收成功

### 回调参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `merchant_no` | string | 商户编号 |
| `order_no` | string | 系统订单号 |
| `out_trade_no` | string | 外部交易号 |
| `order_type` | string | 订单类型：`deposit` / `withdraw` |
| `token` | string | 币种 |
| `chain` | string | 区块链网络 |
| `amount` | string | 订单金额 |
| `fee` | string | 手续费 |
| `net_amount` | string | 净金额 |
| `status` | string | 订单状态 |
| `wallet_address` | string | 钱包地址 |
| `tx_hash` | string | 交易哈希 |
| `confirmations` | int | 确认数 |
| `completed_at` | string | 完成时间（ISO 8601） |
| `extra_data` | string | 附加数据 |
| `timestamp` | int | 回调时间戳（毫秒） |
| `sign` | string | 回调签名 |

### 回调签名验证

签名字段顺序：
```
merchant_no + order_no + status + amount
```

签名密钥：
- 充值订单：使用 `deposit_key`
- 提现订单：使用 `withdraw_key`

### 回调示例

```json
{
  "merchant_no": "M1234567890123",
  "order_no": "DEP1702345678000ABC12345",
  "out_trade_no": "ORDER20231212001",
  "order_type": "deposit",
  "token": "USDT",
  "chain": "tron",
  "amount": "100.00",
  "fee": "0.00",
  "net_amount": "100.00",
  "status": "success",
  "wallet_address": "TXyz...abc",
  "tx_hash": "abc123...xyz",
  "confirmations": 19,
  "completed_at": "2023-12-12T12:05:00Z",
  "extra_data": "{\"user_id\":12345}",
  "timestamp": 1702346700000,
  "sign": "signature_here..."
}
```

### 商户验签示例（Python）

```python
def verify_callback(data: dict, deposit_key: str, withdraw_key: str) -> bool:
    """验证回调签名"""
    sign = data.get('sign')
    order_type = data.get('order_type')
    
    # 选择密钥
    secret_key = deposit_key if order_type == 'deposit' else withdraw_key
    
    # 构建签名消息
    message = (
        data['merchant_no'] +
        data['order_no'] +
        data['status'] +
        data['amount']
    )
    
    # 验证签名
    expected_sign = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_sign.lower(), sign.lower())
```

---

## 订单状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 等待支付（充值）/ 等待处理（提现） |
| `confirming` | 已检测到交易，等待确认 |
| `processing` | 提现处理中 |
| `success` | 已完成 |
| `failed` | 提现失败 |
| `expired` | 充值超时 |

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| `INVALID_MERCHANT` | 无效的商户 |
| `INVALID_SIGNATURE` | 签名验证失败 |
| `TIMESTAMP_EXPIRED` | 请求时间戳过期 |
| `DUPLICATE_REF` | 外部交易号重复 |
| `ORDER_NOT_FOUND` | 订单不存在 |
| `INSUFFICIENT_BALANCE` | 余额不足 |
| `INVALID_ADDRESS` | 无效的钱包地址 |

### 错误响应示例

```json
{
  "success": false,
  "error_code": "INVALID_SIGNATURE",
  "error_message": "Invalid signature"
}
```

---

## 区块链确认数

| 链 | 所需确认数 | 预计时间 |
|----|-----------|---------|
| TRON | 19 | ~1 分钟 |
| Ethereum | 12 | ~3 分钟 |
| Solana | 32 | ~20 秒 |

---

## 安全建议

1. **密钥保管**：妥善保管 `deposit_key` 和 `withdraw_key`，不要泄露
2. **IP 白名单**：建议配置回调 IP 白名单
3. **HTTPS**：回调地址必须使用 HTTPS
4. **签名验证**：务必验证回调签名
5. **幂等处理**：回调可能重复发送，需做幂等处理
6. **金额验证**：收到回调后，验证金额与预期是否一致
