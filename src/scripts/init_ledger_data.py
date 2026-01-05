"""Initialize ledger tables with sample data.

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
    AddressTransaction,
    AddressTransactionType,
    BalanceChangeType,
    BalanceLedger,
    RechargeRecord,
    RechargeStatus,
    RechargeType,
)
from src.models.user import User
from src.models.wallet import Wallet


async def init_ledger_data():
    """Initialize ledger tables with sample data."""
    try:
        async with get_session() as db:
            # 获取用户
            users_result = await db.execute(select(User).limit(5))
            users = users_result.scalars().all()

            if not users:
                print("❌ 没有用户数据，请先创建用户")
                return

            print(f"✅ 找到 {len(users)} 个用户")

            # 获取钱包
            wallets_result = await db.execute(select(Wallet).limit(10))
            wallets = wallets_result.scalars().all()

            print(f"✅ 找到 {len(wallets)} 个钱包")

            # 生成时间范围（最近30天）
            now = datetime.utcnow()

            # ============ 1. 创建地址历史记录 ============
            print("\n📝 创建地址历史记录...")
            address_transactions = []

            for i in range(20):
                user = random.choice(users)
                wallet = random.choice(wallets) if wallets else None
                tx_type = random.choice(
                    [AddressTransactionType.INCOME, AddressTransactionType.EXPENSE]
                )
                token = random.choice(["USDT", "USDC", "TRX"])
                chain = random.choice(["tron", "ethereum", "solana"])
                amount = Decimal(str(round(random.uniform(10, 5000), 2)))

                # 生成随机地址和交易哈希
                address = f"T{
                    ''.join(
                        random.choices(
                            '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=33
                        )
                    )
                }"
                tx_hash = f"{''.join(random.choices('0123456789abcdef', k=64))}"

                created_at = now - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )

                tx = AddressTransaction(
                    user_id=user.id,
                    wallet_id=wallet.id if wallet else None,
                    order_id=None,
                    tx_type=tx_type,
                    token=token,
                    chain=chain,
                    amount=amount,
                    address=address,
                    tx_hash=tx_hash,
                    created_at=created_at,
                )
                address_transactions.append(tx)
                db.add(tx)

            print(f"   ✅ 创建了 {len(address_transactions)} 条地址历史记录")

            # ============ 2. 创建积分明细 ============
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
                            BalanceChangeType.DEPOSIT_INCOME,
                            BalanceChangeType.RECHARGE,
                            BalanceChangeType.FREEZE,
                            BalanceChangeType.UNFREEZE,
                            BalanceChangeType.WITHDRAW_EXPENSE,
                            BalanceChangeType.WITHDRAW_FEE,
                            BalanceChangeType.MANUAL_ADD,
                            BalanceChangeType.MANUAL_DEDUCT,
                        ]
                    )

                    # 根据类型计算金额变化
                    if change_type in [
                        BalanceChangeType.DEPOSIT_INCOME,
                        BalanceChangeType.RECHARGE,
                        BalanceChangeType.MANUAL_ADD,
                    ]:
                        amount = Decimal(str(round(random.uniform(100, 2000), 2)))
                        pre_balance = balance
                        post_balance = balance + amount
                        balance = post_balance
                        frozen_amount = Decimal("0")
                        pre_frozen = frozen
                        post_frozen = frozen
                    elif change_type == BalanceChangeType.FREEZE:
                        amount = Decimal(str(round(random.uniform(50, 500), 2)))
                        pre_balance = balance
                        post_balance = balance - amount
                        balance = post_balance
                        frozen_amount = amount
                        pre_frozen = frozen
                        post_frozen = frozen + amount
                        frozen = post_frozen
                    elif change_type == BalanceChangeType.UNFREEZE:
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
                    else:  # 支出类
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
                        BalanceChangeType.DEPOSIT_INCOME: "用户充值成功",
                        BalanceChangeType.RECHARGE: "管理员充值",
                        BalanceChangeType.FREEZE: "提现申请冻结",
                        BalanceChangeType.UNFREEZE: "提现失败解冻",
                        BalanceChangeType.WITHDRAW_EXPENSE: "提现成功扣款",
                        BalanceChangeType.WITHDRAW_FEE: "提现手续费",
                        BalanceChangeType.MANUAL_ADD: "人工补款",
                        BalanceChangeType.MANUAL_DEDUCT: "人工扣款",
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
                            BalanceChangeType.MANUAL_ADD,
                            BalanceChangeType.MANUAL_DEDUCT,
                            BalanceChangeType.RECHARGE,
                        ]
                        else None,
                        created_at=created_at,
                    )
                    balance_ledgers.append(ledger)
                    db.add(ledger)

            print(f"   ✅ 创建了 {len(balance_ledgers)} 条积分明细")

            # ============ 3. 创建充值记录 ============
            print("\n📝 创建充值记录...")
            recharge_records = []

            for i in range(15):
                user = random.choice(users)
                recharge_type = random.choice(
                    [
                        RechargeType.ONLINE,
                        RechargeType.MANUAL,
                        RechargeType.DEDUCT,
                    ]
                )
                status = random.choice(
                    [
                        RechargeStatus.PENDING,
                        RechargeStatus.SUCCESS,
                        RechargeStatus.SUCCESS,  # 增加成功的概率
                        RechargeStatus.SUCCESS,
                        RechargeStatus.FAILED,
                        RechargeStatus.CANCELLED,
                    ]
                )

                if recharge_type == RechargeType.DEDUCT:
                    amount = -Decimal(str(round(random.uniform(50, 500), 2)))
                else:
                    amount = Decimal(str(round(random.uniform(100, 5000), 2)))

                created_at = now - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )

                completed_at = None
                if status in [RechargeStatus.SUCCESS, RechargeStatus.FAILED]:
                    completed_at = created_at + timedelta(minutes=random.randint(1, 60))

                # 生成充值单号
                recharge_no = (
                    f"RCH{created_at.strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
                )

                remarks = {
                    RechargeType.ONLINE: "在线充值",
                    RechargeType.MANUAL: "管理员手动充值",
                    RechargeType.DEDUCT: "管理员扣款",
                }

                record = RechargeRecord(
                    user_id=user.id,
                    recharge_no=recharge_no,
                    recharge_type=recharge_type,
                    amount=amount,
                    status=status,
                    remark=remarks.get(recharge_type, ""),
                    operator_id=users[0].id if recharge_type != RechargeType.ONLINE else None,
                    completed_at=completed_at,
                    created_at=created_at,
                )
                recharge_records.append(record)
                db.add(record)

            print(f"   ✅ 创建了 {len(recharge_records)} 条充值记录")

            # 提交事务
            await db.commit()
            print("\n🎉 所有数据初始化完成！")

    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(init_ledger_data())
