"""AKX - Payment API endpoints.

This module provides REST API endpoints for payment operations:
- Deposit order creation
- Withdrawal order creation
- Order queries

Business logic is delegated to PaymentService.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import InsufficientBalanceError
from src.db import get_db
from src.models.order import OrderType
from src.schemas.payment import (
    CreateDepositRequest,
    CreateDepositResponse,
    CreateWithdrawRequest,
    CreateWithdrawResponse,
    OrderDetailResponse,
    PaymentErrorCode,
    PaymentErrorResponse,
    QueryOrderByOutTradeNoRequest,
    QueryOrderRequest,
)
from src.services.payment_service import PaymentError, PaymentService

router = APIRouter(prefix="/api/v1/payment", tags=["Payment API"])


# ============ Dependencies ============


def get_payment_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentService:
    """Create PaymentService instance."""
    return PaymentService(db)


# ============ Error Handler ============


def payment_error_response(error: PaymentError, status_code: int = 400) -> JSONResponse:
    """Convert PaymentError to JSON response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": error.code.value,
            "error_message": error.message,
        },
    )


# ============ Deposit Endpoints ============


@router.post(
    "/deposit/create",
    response_model=CreateDepositResponse,
    responses={
        400: {"model": PaymentErrorResponse},
        401: {"model": PaymentErrorResponse},
    },
    summary="创建充值订单",
    description="商户创建充值订单，系统返回充值地址",
)
async def create_deposit(
    request: CreateDepositRequest,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> CreateDepositResponse | JSONResponse:
    """Create a deposit order.

    Signature field order:
    merchant_no + timestamp + nonce + out_trade_no + token + chain + amount + callback_url
    """
    try:
        # Build signature message
        sign_message = (
            f"{request.merchant_no}"
            f"{request.timestamp}"
            f"{request.nonce}"
            f"{request.out_trade_no}"
            f"{request.token}"
            f"{request.chain}"
            f"{request.amount}"
            f"{request.callback_url}"
        )

        # Authenticate request
        merchant = await service.authenticate_deposit_request(
            merchant_no=request.merchant_no,
            timestamp=request.timestamp,
            nonce=request.nonce,
            signature=request.sign,
            signature_message=sign_message,
        )

        # Validate token and chain
        token, chain = await service.validate_token_chain(request.token, request.chain)

        # Create order
        order = await service.create_deposit_order(
            merchant=merchant,
            out_trade_no=request.out_trade_no,
            token=token,
            chain=chain,
            amount=Decimal(request.amount),
            callback_url=request.callback_url,
            extra_data=request.extra_data,
        )

        return CreateDepositResponse(
            success=True,
            order_no=order.order_no,
            out_trade_no=order.out_trade_no,
            token=order.token,
            chain=order.chain,
            amount=str(order.amount),
            wallet_address=order.wallet_address or "",
            expire_time=order.expire_time,
            created_at=order.created_at,
        )

    except PaymentError as e:
        status_code = (
            401
            if e.code
            in (
                PaymentErrorCode.INVALID_MERCHANT,
                PaymentErrorCode.INVALID_SIGNATURE,
                PaymentErrorCode.TIMESTAMP_EXPIRED,
            )
            else 400
        )
        return payment_error_response(e, status_code)
    except InsufficientBalanceError as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INSUFFICIENT_BALANCE, e.message),
            400,
        )
    except Exception as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INTERNAL_ERROR, str(e)),
            500,
        )


# ============ Withdraw Endpoints ============


@router.post(
    "/withdraw/create",
    response_model=CreateWithdrawResponse,
    responses={
        400: {"model": PaymentErrorResponse},
        401: {"model": PaymentErrorResponse},
    },
    summary="创建提现订单",
    description="商户创建提现订单，系统处理打款",
)
async def create_withdraw(
    request: CreateWithdrawRequest,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> CreateWithdrawResponse | JSONResponse:
    """Create a withdrawal order.

    Signature field order:
    merchant_no + timestamp + nonce + out_trade_no + token + chain + amount
    + to_address + callback_url
    """
    try:
        # Build signature message
        sign_message = (
            f"{request.merchant_no}"
            f"{request.timestamp}"
            f"{request.nonce}"
            f"{request.out_trade_no}"
            f"{request.token}"
            f"{request.chain}"
            f"{request.amount}"
            f"{request.to_address}"
            f"{request.callback_url}"
        )

        # Authenticate request
        merchant = await service.authenticate_withdraw_request(
            merchant_no=request.merchant_no,
            timestamp=request.timestamp,
            nonce=request.nonce,
            signature=request.sign,
            signature_message=sign_message,
        )

        # Validate token and chain
        token, chain = await service.validate_token_chain(request.token, request.chain)

        # Create order
        order = await service.create_withdraw_order(
            merchant=merchant,
            out_trade_no=request.out_trade_no,
            token=token,
            chain=chain,
            amount=Decimal(request.amount),
            to_address=request.to_address,
            callback_url=request.callback_url,
            extra_data=request.extra_data,
        )

        # Trigger async withdrawal processing (via Celery)
        from src.tasks.callback import process_withdraw_order

        process_withdraw_order.delay(order.id)

        return CreateWithdrawResponse(
            success=True,
            order_no=order.order_no,
            out_trade_no=order.out_trade_no,
            token=order.token,
            chain=order.chain,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            to_address=order.to_address or "",
            status=order.status.value,
            created_at=order.created_at,
        )

    except PaymentError as e:
        status_code = (
            401
            if e.code
            in (
                PaymentErrorCode.INVALID_MERCHANT,
                PaymentErrorCode.INVALID_SIGNATURE,
                PaymentErrorCode.TIMESTAMP_EXPIRED,
            )
            else 400
        )
        return payment_error_response(e, status_code)
    except InsufficientBalanceError as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INSUFFICIENT_BALANCE, e.message),
            400,
        )
    except Exception as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INTERNAL_ERROR, str(e)),
            500,
        )


# ============ Query Endpoints ============


@router.post(
    "/order/query",
    response_model=OrderDetailResponse,
    responses={
        400: {"model": PaymentErrorResponse},
        401: {"model": PaymentErrorResponse},
        404: {"model": PaymentErrorResponse},
    },
    summary="查询订单（按订单号）",
    description="通过系统订单号查询订单详情",
)
async def query_order(
    request: QueryOrderRequest,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> OrderDetailResponse | JSONResponse:
    """Query order by system order number.

    Signature field order:
    merchant_no + timestamp + nonce + order_no
    """
    try:
        # Build signature message
        sign_message = f"{request.merchant_no}{request.timestamp}{request.nonce}{request.order_no}"

        # Try to authenticate with deposit key first, then withdraw key
        merchant = None
        try:
            merchant = await service.authenticate_deposit_request(
                merchant_no=request.merchant_no,
                timestamp=request.timestamp,
                nonce=request.nonce,
                signature=request.sign,
                signature_message=sign_message,
            )
        except PaymentError:
            merchant = await service.authenticate_withdraw_request(
                merchant_no=request.merchant_no,
                timestamp=request.timestamp,
                nonce=request.nonce,
                signature=request.sign,
                signature_message=sign_message,
            )

        # Get order
        order = await service.get_order_by_no(request.order_no, merchant.id)
        if not order:
            return payment_error_response(
                PaymentError(PaymentErrorCode.ORDER_NOT_FOUND, "Order not found"),
                404,
            )

        return OrderDetailResponse(
            success=True,
            order_no=order.order_no,
            out_trade_no=order.out_trade_no,
            order_type=order.order_type.value,
            token=order.token,
            chain=order.chain,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            status=order.status.value,
            wallet_address=order.wallet_address,
            to_address=order.to_address,
            tx_hash=order.tx_hash,
            confirmations=order.confirmations,
            created_at=order.created_at,
            completed_at=order.completed_at,
            extra_data=order.extra_data,
        )

    except PaymentError as e:
        status_code = (
            401
            if e.code
            in (
                PaymentErrorCode.INVALID_MERCHANT,
                PaymentErrorCode.INVALID_SIGNATURE,
                PaymentErrorCode.TIMESTAMP_EXPIRED,
            )
            else 400
        )
        return payment_error_response(e, status_code)
    except Exception as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INTERNAL_ERROR, str(e)),
            500,
        )


@router.post(
    "/order/query-by-out-trade-no",
    response_model=OrderDetailResponse,
    responses={
        400: {"model": PaymentErrorResponse},
        401: {"model": PaymentErrorResponse},
        404: {"model": PaymentErrorResponse},
    },
    summary="查询订单（按外部交易号）",
    description="通过商户外部交易号查询订单详情",
)
async def query_order_by_out_trade_no(
    request: QueryOrderByOutTradeNoRequest,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> OrderDetailResponse | JSONResponse:
    """Query order by external trade number.

    Signature field order:
    merchant_no + timestamp + nonce + out_trade_no + order_type
    """
    try:
        # Build signature message
        sign_message = (
            f"{request.merchant_no}"
            f"{request.timestamp}"
            f"{request.nonce}"
            f"{request.out_trade_no}"
            f"{request.order_type.value}"
        )

        # Authenticate based on order type
        if request.order_type.value == "deposit":
            merchant = await service.authenticate_deposit_request(
                merchant_no=request.merchant_no,
                timestamp=request.timestamp,
                nonce=request.nonce,
                signature=request.sign,
                signature_message=sign_message,
            )
            order_type = OrderType.DEPOSIT
        else:
            merchant = await service.authenticate_withdraw_request(
                merchant_no=request.merchant_no,
                timestamp=request.timestamp,
                nonce=request.nonce,
                signature=request.sign,
                signature_message=sign_message,
            )
            order_type = OrderType.WITHDRAW

        # Get order
        order = await service.get_order_by_out_trade_no(
            request.out_trade_no,
            merchant.id,
            order_type,
        )
        if not order:
            return payment_error_response(
                PaymentError(PaymentErrorCode.ORDER_NOT_FOUND, "Order not found"),
                404,
            )

        return OrderDetailResponse(
            success=True,
            order_no=order.order_no,
            out_trade_no=order.out_trade_no,
            order_type=order.order_type.value,
            token=order.token,
            chain=order.chain,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            status=order.status.value,
            wallet_address=order.wallet_address,
            to_address=order.to_address,
            tx_hash=order.tx_hash,
            confirmations=order.confirmations,
            created_at=order.created_at,
            completed_at=order.completed_at,
            extra_data=order.extra_data,
        )

    except PaymentError as e:
        status_code = (
            401
            if e.code
            in (
                PaymentErrorCode.INVALID_MERCHANT,
                PaymentErrorCode.INVALID_SIGNATURE,
                PaymentErrorCode.TIMESTAMP_EXPIRED,
            )
            else 400
        )
        return payment_error_response(e, status_code)
    except Exception as e:
        return payment_error_response(
            PaymentError(PaymentErrorCode.INTERNAL_ERROR, str(e)),
            500,
        )
