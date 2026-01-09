"""AKX Crypto Payment Gateway - Payment API schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# Common
# ============================================================================


class PaymentBaseRequest(BaseModel):
    """Base request with common fields for all payment APIs."""

    merchant_no: str = Field(..., description="商户编号")
    timestamp: int = Field(..., description="请求时间戳（毫秒）")
    nonce: str = Field(..., min_length=16, max_length=32, description="随机字符串")
    sign: str = Field(..., description="HMAC-SHA256 签名")


class OrderTypeEnum(str, Enum):
    """Order type for query."""

    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"


# ============================================================================
# Deposit
# ============================================================================


class CreateDepositRequest(PaymentBaseRequest):
    """Create deposit order request."""

    out_trade_no: str = Field(..., max_length=64, description="外部交易号")
    token: str = Field(..., description="币种：USDT / USDC / ETH / TRX / SOL")
    chain: str = Field(..., description="区块链网络：tron / ethereum / solana")
    amount: str = Field(..., description="金额（最多8位小数）")
    currency: str = Field(
        default="USDT",
        description="金额币种：USDT(加密货币原价) / CNY / USD 等法币代码",
    )
    callback_url: str = Field(..., max_length=500, description="回调通知地址")
    extra_data: str | None = Field(None, max_length=1024, description="附加数据")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is a valid decimal."""
        try:
            amount = Decimal(v)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            # Check decimal places
            if abs(amount.as_tuple().exponent) > 8:
                raise ValueError("Amount can have at most 8 decimal places")
        except Exception as e:
            raise ValueError(f"Invalid amount: {e}")
        return v


class CreateDepositResponse(BaseModel):
    """Create deposit order response."""

    success: bool = True
    order_no: str = Field(..., description="系统订单号")
    out_trade_no: str = Field(..., description="外部交易号")
    token: str = Field(..., description="币种")
    chain: str = Field(..., description="区块链网络")
    requested_currency: str = Field(..., description="请求的币种")
    requested_amount: str = Field(..., description="请求的原始金额")
    exchange_rate: str | None = Field(None, description="汇率（法币订单时有值）")
    amount: str = Field(..., description="实际支付金额（含防重复尾数）")
    wallet_address: str = Field(..., description="充值地址")
    cashier_url: str = Field(..., description="收银台页面链接")
    expire_time: datetime = Field(..., description="过期时间")
    created_at: datetime = Field(..., description="创建时间")


# ============================================================================
# Withdraw
# ============================================================================


class CreateWithdrawRequest(PaymentBaseRequest):
    """Create withdraw order request."""

    out_trade_no: str = Field(..., max_length=64, description="外部交易号")
    token: str = Field(..., description="币种：USDT / USDC / ETH / TRX / SOL")
    chain: str = Field(..., description="区块链网络：tron / ethereum / solana")
    amount: str = Field(..., description="提现金额（最多8位小数）")
    to_address: str = Field(..., max_length=200, description="收款钱包地址")
    callback_url: str = Field(..., max_length=500, description="回调通知地址")
    extra_data: str | None = Field(None, max_length=1024, description="附加数据")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        """Validate amount is a valid decimal."""
        try:
            amount = Decimal(v)
            if amount <= 0:
                raise ValueError("Amount must be positive")
            if abs(amount.as_tuple().exponent) > 8:
                raise ValueError("Amount can have at most 8 decimal places")
        except Exception as e:
            raise ValueError(f"Invalid amount: {e}")
        return v


class CreateWithdrawResponse(BaseModel):
    """Create withdraw order response."""

    success: bool = True
    order_no: str = Field(..., description="系统订单号")
    out_trade_no: str = Field(..., description="外部交易号")
    token: str = Field(..., description="币种")
    chain: str = Field(..., description="区块链网络")
    amount: str = Field(..., description="提现金额")
    fee: str = Field(..., description="手续费")
    net_amount: str = Field(..., description="实际到账金额")
    to_address: str = Field(..., description="收款地址")
    status: str = Field(..., description="订单状态")
    created_at: datetime = Field(..., description="创建时间")


# ============================================================================
# Query
# ============================================================================


class QueryOrderRequest(PaymentBaseRequest):
    """Query order by system order_no."""

    order_no: str = Field(..., description="系统订单号")


class QueryOrderByOutTradeNoRequest(PaymentBaseRequest):
    """Query order by external out_trade_no."""

    out_trade_no: str = Field(..., description="外部交易号")
    order_type: OrderTypeEnum = Field(..., description="订单类型：deposit / withdraw")


class OrderDetailResponse(BaseModel):
    """Order detail response."""

    success: bool = True
    order_no: str = Field(..., description="系统订单号")
    out_trade_no: str = Field(..., description="外部交易号")
    order_type: str = Field(..., description="订单类型")
    token: str = Field(..., description="币种")
    chain: str = Field(..., description="区块链网络")
    amount: str = Field(..., description="订单金额")
    fee: str = Field(..., description="手续费")
    net_amount: str = Field(..., description="净金额")
    status: str = Field(..., description="订单状态")
    wallet_address: str | None = Field(None, description="钱包地址")
    to_address: str | None = Field(None, description="收款地址（提现）")
    tx_hash: str | None = Field(None, description="交易哈希")
    confirmations: int = Field(0, description="确认数")
    created_at: datetime = Field(..., description="创建时间")
    completed_at: datetime | None = Field(None, description="完成时间")
    extra_data: str | None = Field(None, description="附加数据")


# ============================================================================
# Callback
# ============================================================================


class CallbackPayload(BaseModel):
    """Callback notification payload sent to merchant."""

    merchant_no: str = Field(..., description="商户编号")
    order_no: str = Field(..., description="系统订单号")
    out_trade_no: str = Field(..., description="外部交易号")
    order_type: str = Field(..., description="订单类型")
    token: str = Field(..., description="币种")
    chain: str = Field(..., description="区块链网络")
    amount: str = Field(..., description="订单金额")
    fee: str = Field(..., description="手续费")
    net_amount: str = Field(..., description="净金额")
    status: str = Field(..., description="订单状态")
    wallet_address: str | None = Field(None, description="钱包地址")
    to_address: str | None = Field(None, description="收款地址")
    tx_hash: str | None = Field(None, description="交易哈希")
    confirmations: int = Field(0, description="确认数")
    completed_at: str | None = Field(None, description="完成时间（ISO 8601）")
    extra_data: str | None = Field(None, description="附加数据")
    timestamp: int = Field(..., description="回调时间戳（毫秒）")
    sign: str = Field(..., description="回调签名")


# ============================================================================
# Errors
# ============================================================================


class PaymentErrorResponse(BaseModel):
    """Payment API error response."""

    success: bool = False
    error_code: str = Field(..., description="错误码")
    error_message: str = Field(..., description="错误信息")


class PaymentErrorCode(str, Enum):
    """Payment error codes."""

    INVALID_MERCHANT = "INVALID_MERCHANT"  # 无效的商户
    INVALID_SIGNATURE = "INVALID_SIGNATURE"  # 签名验证失败
    TIMESTAMP_EXPIRED = "TIMESTAMP_EXPIRED"  # 请求时间戳过期
    DUPLICATE_REF = "DUPLICATE_REF"  # 外部交易号重复
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"  # 订单不存在
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"  # 余额不足
    INVALID_ADDRESS = "INVALID_ADDRESS"  # 无效的钱包地址
    INVALID_TOKEN_CHAIN = "INVALID_TOKEN_CHAIN"  # 无效的币种或链
    AMOUNT_TOO_SMALL = "AMOUNT_TOO_SMALL"  # 金额低于最小限额
    NO_AVAILABLE_ADDRESS = "NO_AVAILABLE_ADDRESS"  # 无可用充值地址
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 内部错误
