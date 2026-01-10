"""
AKX 支付网关 API 调用示例

商户号：M3
币种：USDT（大写）
链：TRON（大写）

新功能：支持法币金额创建订单
- 直接使用 USDT 金额：currency="USDT"（默认）
- 使用法币金额：currency="CNY"/"USD" 等，系统自动按汇率计算 USDT
"""

import hashlib
import hmac
import secrets
import time

import requests

# ============== 配置信息 ==============
BASE_URL = "http://localhost:8000"  # 本地测试环境，生产环境改为 https://api.akx.com

MERCHANT_NO = "M3"
DEPOSIT_KEY = "be9907aae0f3e532f24ece688f6dcb6114d1fce085abd60795ae9670923e83c1"
WITHDRAW_KEY = "b77187fa76419ecf455dc8233ff7ab281184fff2e1d90c2bb97476fbb707d74f"

# 默认币种和链（推荐使用大写格式）
TOKEN = "USDT"
CHAIN = "TRON"


def generate_sign(message: str, secret_key: str) -> str:
    """生成 HMAC-SHA256 签名"""
    return hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_timestamp() -> int:
    """获取毫秒时间戳"""
    return int(time.time() * 1000)


def get_nonce() -> str:
    """生成 32 位随机字符串"""
    return secrets.token_hex(16)


# ============== 充值订单 ==============
def create_deposit_order(
    out_trade_no: str,
    amount: str,
    callback_url: str,
    currency: str = "USDT",
    extra_data: str | None = None,
) -> dict:
    """
    创建充值订单

    Args:
        out_trade_no: 商户订单号（唯一）
        amount: 金额（根据 currency 决定是 USDT 还是法币）
        callback_url: 回调通知地址
        currency: 金额币种，默认 USDT。可传 CNY/USD 等法币代码
        extra_data: 附加数据（可选）

    Returns:
        API 响应结果
    """
    timestamp = get_timestamp()
    nonce = get_nonce()

    # 签名字段顺序：
    # merchant_no + timestamp + nonce + out_trade_no + token + chain
    # + amount + currency + callback_url
    sign_message = (
        f"{MERCHANT_NO}{timestamp}{nonce}{out_trade_no}"
        f"{TOKEN}{CHAIN}{amount}{currency}{callback_url}"
    )
    sign = generate_sign(sign_message, DEPOSIT_KEY)

    # 构建请求体
    payload = {
        "merchant_no": MERCHANT_NO,
        "timestamp": timestamp,
        "nonce": nonce,
        "out_trade_no": out_trade_no,
        "token": TOKEN,
        "chain": CHAIN,
        "amount": amount,
        "currency": currency,
        "callback_url": callback_url,
        "sign": sign,
    }

    if extra_data:
        payload["extra_data"] = extra_data

    # 发送请求
    url = f"{BASE_URL}/api/v1/payment/deposit/create"
    response = requests.post(url, json=payload, timeout=30)

    print(f"\n{'=' * 50}")
    print(f"【创建充值订单】- 金额币种: {currency}")
    print(f"请求 URL: {url}")
    print(f"请求参数: {payload}")
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.json()}")
    print(f"{'=' * 50}\n")

    return response.json()


# ============== 代付（提现）订单 ==============
def create_withdraw_order(
    out_trade_no: str,
    amount: str,
    to_address: str,
    callback_url: str,
    extra_data: str | None = None,
) -> dict:
    """
    创建代付（提现）订单

    Args:
        out_trade_no: 商户订单号（唯一）
        amount: 提现金额
        to_address: 收款钱包地址
        callback_url: 回调通知地址
        extra_data: 附加数据（可选）

    Returns:
        API 响应结果
    """
    timestamp = get_timestamp()
    nonce = get_nonce()

    # 签名字段顺序：
    # merchant_no + timestamp + nonce + out_trade_no + token
    # + chain + amount
    # + to_address + callback_url
    sign_message = (
        f"{MERCHANT_NO}"
        f"{timestamp}"
        f"{nonce}"
        f"{out_trade_no}"
        f"{TOKEN}"
        f"{CHAIN}"
        f"{amount}"
        f"{to_address}"
        f"{callback_url}"
    )
    sign = generate_sign(sign_message, WITHDRAW_KEY)

    # 构建请求体
    payload = {
        "merchant_no": MERCHANT_NO,
        "timestamp": timestamp,
        "nonce": nonce,
        "out_trade_no": out_trade_no,
        "token": TOKEN,
        "chain": CHAIN,
        "amount": amount,
        "to_address": to_address,
        "callback_url": callback_url,
        "sign": sign,
    }

    if extra_data:
        payload["extra_data"] = extra_data

    # 发送请求
    url = f"{BASE_URL}/api/v1/payment/withdraw/create"
    response = requests.post(url, json=payload, timeout=30)

    print(f"\n{'=' * 50}")
    print("【创建代付（提现）订单】")
    print(f"请求 URL: {url}")
    print(f"请求参数: {payload}")
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.json()}")
    print(f"{'=' * 50}\n")

    return response.json()


# ============== 查询订单 ==============
def query_order(order_no: str, is_deposit: bool = True) -> dict:
    """
    查询订单（按系统订单号）

    Args:
        order_no: 系统订单号
        is_deposit: 是否为充值订单（决定使用哪个密钥）

    Returns:
        API 响应结果
    """
    timestamp = get_timestamp()
    nonce = get_nonce()

    # 签名字段顺序：merchant_no + timestamp + nonce + order_no
    sign_message = f"{MERCHANT_NO}{timestamp}{nonce}{order_no}"
    secret_key = DEPOSIT_KEY if is_deposit else WITHDRAW_KEY
    sign = generate_sign(sign_message, secret_key)

    payload = {
        "merchant_no": MERCHANT_NO,
        "timestamp": timestamp,
        "nonce": nonce,
        "order_no": order_no,
        "sign": sign,
    }

    url = f"{BASE_URL}/api/v1/payment/order/query"
    response = requests.post(url, json=payload, timeout=30)

    print(f"\n{'=' * 50}")
    print(f"【查询订单】- {'充值' if is_deposit else '提现'}")
    print(f"请求 URL: {url}")
    print(f"请求参数: {payload}")
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.json()}")
    print(f"{'=' * 50}\n")

    return response.json()


# ============== 测试入口 ==============
if __name__ == "__main__":
    # 生成唯一订单号
    order_suffix = int(time.time())

    # 测试充值（直接使用 USDT 金额）
    print("\n" + "=" * 60)
    print("测试 1: 创建充值订单（USDT 金额）")
    print("=" * 60)
    deposit_result = create_deposit_order(
        out_trade_no=f"DEP_TEST_{order_suffix}",
        amount="100.00",
        callback_url="http://localhost:8000/api/v1/payment/test-callback",
        currency="USDT",  # 默认值，可省略
        extra_data='{"user_id": 12345, "remark": "测试充值"}',
    )

    # 测试充值（使用法币金额，系统自动计算 USDT）
    print("\n" + "=" * 60)
    print("测试 2: 创建充值订单（CNY 金额，自动换算）")
    print("=" * 60)
    deposit_cny_result = create_deposit_order(
        out_trade_no=f"DEP_CNY_{order_suffix}",
        amount="100.00",  # 100 CNY
        callback_url="https://example.com/callback/deposit",
        currency="CNY",  # 使用人民币金额
        extra_data='{"user_id": 12345, "remark": "测试 CNY 充值"}',
    )

    # 测试代付（提现）
    print("\n" + "=" * 60)
    print("测试 3: 创建代付（提现）订单")
    print("=" * 60)
    withdraw_result = create_withdraw_order(
        out_trade_no=f"WD_TEST_{order_suffix}",
        amount="50.00",
        to_address="T4A1DEE1PtkVi4sYvfSGhBYJ3LLCheC394",  # 替换为实际的 TRON 地址
        callback_url="https://example.com/callback/withdraw",
        extra_data='{"user_id": 12345, "remark": "测试提现"}',
    )

    # 测试查询订单（如果创建成功）
    if deposit_result.get("success") and deposit_result.get("order_no"):
        print("\n" + "=" * 60)
        print("测试 4: 查询充值订单")
        print("=" * 60)
        query_order(deposit_result["order_no"], is_deposit=True)

    if withdraw_result.get("success") and withdraw_result.get("order_no"):
        print("\n" + "=" * 60)
        print("测试 5: 查询提现订单")
        print("=" * 60)
        query_order(withdraw_result["order_no"], is_deposit=False)
