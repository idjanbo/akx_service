"""Add more recharge records with linked balance ledgers.

Run with:
    cd /Users/djanbo/www/akx/akx_service
    uv run python -m src.scripts.add_recharge_records
"""

import asyncio
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import select

from src.db.engine import close_db, get_session
from src.models.ledger import (
    BalanceChangeType,
    BalanceLedger,
    RechargeRecord,
    RechargeStatus,
    RechargeType,
)
from src.models.user import User


async def add_recharge_records():
    """Add recharge records with linked balance ledgers."""
    try:
        async with get_session() as db:
            # 获取用户
            users_result = await db.execute(select(User).limit(5))
            users = users_result.scalars().all()

            if not users:
                print("❌ 没有用户数据，请先创建用户")
                return

            print(f"✅ 找到 {len(users)} 个用户")

            now = datetime.utcnow()
            recharge_count = 0

            for user in users:
                # 初始余额
                balance = Decimal("10000")

                # 每个用户创建 5-8 条充值记录
                for _ in range(random.randint(5, 8)):
                    recharge_type = random.choice(
                        [
                            RechargeType.ONLINE,
                            RechargeType.ONLINE,
                            RechargeType.MANUAL,
                            RechargeType.DEDUCT,
                        ]
                    )

                    status = random.choice(
                        [
                            RechargeStatus.PENDING,
                            RechargeStatus.SUCCESS,
                            RechargeStatus.SUCCESS,
                            RechargeStatus.SUCCESS,
                            RechargeStatus.FAILED,
                            RechargeStatus.CANCELLED,
                        ]
                    )

                    # 金额
                    if recharge_type == RechargeType.DEDUCT:
                        amount = -Decimal(str(round(random.uniform(50, 500), 2)))
                    else:
                        amount = Decimal(str(round(random.uniform(100, 5000), 2)))

                    # 时间
                    created_at = now - timedelta(
                        days=random.randint(0, 30),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )

                    completed_at = None
                    if status in [RechargeStatus.SUCCESS, RechargeStatus.FAILED]:
                        completed_at = created_at + timedelta(minutes=random.randint(1, 60))

                    # 备注
                    remarks = {
                        RechargeType.ONLINE: "在线充值",
                        RechargeType.MANUAL: "管理员手动充值",
                        RechargeType.DEDUCT: "管理员扣款",
                    }

                    # 支付方式（仅在线充值有）
                    payment_methods = ["支付宝", "微信", "银行卡", "USDT"]
                    payment_method = (
                        random.choice(payment_methods)
                        if recharge_type == RechargeType.ONLINE
                        else None
                    )

                    ledger_id = None

                    # 如果是成功状态，创建关联的积分明细
                    if status == RechargeStatus.SUCCESS:
                        pre_balance = balance
                        post_balance = balance + amount
                        balance = post_balance

                        # 确定账变类型
                        if recharge_type == RechargeType.DEDUCT:
                            change_type = BalanceChangeType.MANUAL_DEDUCT
                        elif recharge_type == RechargeType.MANUAL:
                            change_type = BalanceChangeType.MANUAL_ADD
                        else:
                            change_type = BalanceChangeType.RECHARGE

                        # 创建积分明细
                        ledger = BalanceLedger(
                            user_id=user.id,
                            order_id=None,
                            change_type=change_type,
                            amount=amount,
                            pre_balance=pre_balance,
                            post_balance=post_balance,
                            frozen_amount=Decimal("0"),
                            pre_frozen=Decimal("0"),
                            post_frozen=Decimal("0"),
                            remark=remarks.get(recharge_type, ""),
                            operator_id=users[0].id
                            if recharge_type != RechargeType.ONLINE
                            else None,
                            created_at=completed_at or created_at,
                        )
                        db.add(ledger)
                        await db.flush()  # 获取 ledger.id
                        await db.refresh(ledger)  # 确保获取到数据库生成的 id
                        ledger_id = ledger.id
                        print(f"   创建积分明细 #{ledger_id}, post_balance={post_balance}")

                    # 创建充值记录
                    record = RechargeRecord(
                        user_id=user.id,
                        ledger_id=ledger_id,
                        recharge_type=recharge_type,
                        amount=amount,
                        status=status,
                        payment_method=payment_method,
                        remark=remarks.get(recharge_type, ""),
                        operator_id=users[0].id if recharge_type != RechargeType.ONLINE else None,
                        completed_at=completed_at,
                        created_at=created_at,
                    )
                    db.add(record)
                    await db.flush()
                    await db.refresh(record)
                    print(f"   创建充值记录 #{record.id}, ledger_id={record.ledger_id}")
                    recharge_count += 1

            await db.commit()
            print(f"\n🎉 成功创建 {recharge_count} 条充值记录！")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(add_recharge_records())
