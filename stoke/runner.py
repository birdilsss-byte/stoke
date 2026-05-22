"""
每日主流程 — 串联所有层的调度入口

不搞调度框架，一个小函数就够。
流程：盘前预热 → 时机判断 → 风控检查 → 发现候选 → 模拟执行 → 盘后沉淀
"""

import logging
from datetime import datetime

from stoke import Stoke
from stoke.context import MarketContext
from stoke.timing import Timing
from stoke.discovery import Discovery
from stoke.execute import Executor
from stoke.journal import Journal
from stoke.backtest import ma_cross, breakout, volume_surge, macd

logger = logging.getLogger(__name__)


def daily_routine() -> MarketContext:
    """
    每日量化主流程

    Returns:
        MarketContext — 包含市场阶段、风险等级、建议仓位、候选标的、持仓
    """
    s = Stoke()  # StokeCached（带缓存），warmup 需传裸 Stoke 实例避免缓存回环
    ctx = MarketContext()
    ctx.trade_date = datetime.now().date()
    ctx.last_update = datetime.now().isoformat()
    ctx.active_strategies = {
        "均线金叉": ma_cross,
        "突破策略": breakout,
        "放量策略": volume_surge,
    }
    journal = Journal(s.store)
    executor = Executor(s, ctx)

    # 1. 盘前预热（传裸 Stoke，避免缓存回环）
    logger.info("===== Step 1/6: 盘前预热 =====")
    s.store.warmup(s._s)

    # 2. 时机判断（大脑）
    logger.info("===== Step 2/6: 时机评估 =====")
    timing = Timing(s, ctx)
    timing.assess()
    logger.info(
        "市场阶段=%s 风险=%d/10 建议仓位=%.0f%%",
        ctx.market_phase, ctx.risk_level, ctx.position_advice * 100,
    )

    # 3. 风控检查
    if ctx.risk_level >= 8:
        logger.warning("风控过高(%d/10)，今日不开仓", ctx.risk_level)
        return ctx

    # 4. 发现候选（眼睛）
    logger.info("===== Step 3/6: 发现候选 =====")
    discovery = Discovery(s, ctx)
    discovery.scan()
    logger.info("候选标的: %d 只", len(ctx.candidates))

    # 5. 检查止损止盈
    logger.info("===== Step 4/6: 持仓检查 =====")
    sell_orders = executor.check_stop(ctx.positions)
    for order in sell_orders:
        journal.log_trade(order.__dict__)

    # 6. 模拟执行（手）
    logger.info("===== Step 5/6: 策略执行 =====")
    for strategy_name in ctx.active_strategies:
        for c in ctx.candidates[:3]:
            order = executor.place(c, strategy_name)
            if order:
                journal.log_trade(order.__dict__)

    # 7. 盘后沉淀（记忆）
    logger.info("===== Step 6/6: 盘后沉淀 =====")
    logger.info("持仓: %d 只, 候选: %d 只",
                 len(ctx.positions), len(ctx.candidates))

    logger.info("===== 每日流程完成 =====")
    return ctx
