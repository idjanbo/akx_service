"""Initialize balance ledger with sample data.

Run with:
    cd /Users/djanbo/www/akx/akx_service
    uv run python -m src.scripts.init_ledger_data
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
)
from src.models.user import User


async def init_ledger_data():
    """Initialize balance ledger with sample data."""
    try:
        async with get_session() as db:
            # 获取用户
            users_result = await db.execute(select(User).limit(5))
            users = users_result.scalars().all()

            if not users:
                print("❌ 没有用户数据，请先创建用户")
                return

            print(f"✅ 找到 {len(users)} 个用户")

            # 生成时间范围（最近30天）
            now = datetime.utcnow()

            # ============ 创建积分明细 ============
            print("\n📝 创建积分明细...")
            balance_ledgers = []

            # 每个用户创建多条记录
            for user in users:
                balance = Decimal("10000")  # 初始余额
                frozen = Decimal("0")

                # 为每个用户创建 5-10 条记录
                for j in range(random.randint(5, 10)):
                    change_type = random.choice(
                        [
                            BalanceChangeType.ONLINE_RECHARGE,
                            BalanceChangeType.MANUAL_RECHARGE,
                            BalanceChangeType.MANUAL_DEDUCT,
                            BalanceChangeType.FEE_FREEZE,
                            BalanceChangeType.FEE_UNFREEZE,
                            BalanceChangeType.FEE_SETTLE,
                            BalanceChangeType.REFUND,
                            BalanceChangeType.ADJUSTMENT,
                        ]
                    )

                    # 根据类型计算金额变化
                    if change_type in [
                        BalanceChangeType.ONLINE_RECHARGE,
                        BalanceChangeType.MANUAL_RECHARGE,
                        BalanceChangeType.REFUND,
                    ]:
                        amount = Decimal(str(round(random.uniform(100, 2000), 2)))
                        pre_balance = balance
                        post_balance = balance + amount
                        balance = post_balance
                        frozen_amount = Decimal("0")
                        pre_frozen = frozen
                        post_frozen = frozen
                    elif change_type == BalanceChangeType.FEE_FREEZE:
                        amount = Decimal(str(round(random.uniform(50, 500), 2)))
                        pre_balance = balance
                        post_balance = balance - amount
                        balance = post_balance
                        frozen_amount = amount
                        pre_frozen = frozen
                        post_frozen = frozen + amount
                        frozen = post_frozen
                    elif change_type == BalanceChangeType.FEE_UNFREEZE:
                        if frozen > 0:
                            amount = min(Decimal(str(round(random.uniform(50, 200), 2))), frozen)
                            pre_balance = balance
                            post_balance = balance + amount
                            balance = post_balance
                            frozen_amount = -amount
                            pre_frozen = frozen
                            post_frozen = frozen - amount
                            frozen = post_frozen
                        else:
                            continue
                    else:  # 支出类 (MANUAL_DEDUCT, FEE_SETTLE)
                        amount = -Decimal(str(round(random.uniform(50, 500), 2)))
                        pre_balance = balance
                        post_balance = max(balance + amount, Decimal("0"))
                        balance = post_balance
                        frozen_amount = Decimal("0")
                        pre_frozen = frozen
                        post_frozen = frozen

                    created_at = now - timedelta(
                        days=random.randint(0, 30),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59),
                    )

                    remarks = {
                        BalanceChangeType.ONLINE_RECHARGE: "在线充值",
                        BalanceChangeType.MANUAL_RECHARGE: "人工充值",
                        BalanceChangeType.MANUAL_DEDUCT: "人工扣款",
                        BalanceChangeType.FEE_FREEZE: "手续费冻结",
                        BalanceChangeType.FEE_UNFREEZE: "手续费解冻",
                        BalanceChangeType.FEE_SETTLE: "手续费结算",
                        BalanceChangeType.REFUND: "退款",
                        BalanceChangeType.ADJUSTMENT: "调账",
                    }

                    ledger = BalanceLedger(
                        user_id=user.id,
                        order_id=None,
                        change_type=change_type,
                        amount=amount,
                        pre_balance=pre_balance,
                        post_balance=post_balance,
                        frozen_amount=frozen_amount,
                        pre_frozen=pre_frozen,
                        post_frozen=post_frozen,
                        remark=remarks.get(change_type, ""),
                        operator_id=users[0].id
                        if change_type
                        in [
                            BalanceChangeType.MANUAL_RECHARGE,
                            BalanceChangeType.MANUAL_DEDUCT,
                            BalanceChangeType.ADJUSTMENT,
                        ]
                        else None,
                        created_at=created_at,
                    )
                    balance_ledgers.append(ledger)
                    db.add(ledger)

            print(f"   ✅ 创建了 {len(balance_ledgers)} 条积分明细")

            # 提交事务
            await db.commit()
            print("\n🎉 所有数据初始化完成！")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(init_ledger_data())
