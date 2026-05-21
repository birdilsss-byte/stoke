"""
每日主流程 — 串联所有层的调度入口

不搞调度框架，一个小函数就够。
流程：盘前预热 → 时机判断 → 风控检查 → 发现候选
"""

import logging
from datetime import datetime

from stoke import Stoke
from stoke.context import MarketContext
from stoke.timing import Timing
from stoke.discovery import Discovery

logger = logging.getLogger(__name__)


def daily_routine() -> MarketContext:
    """
    每日量化主流程

    Returns:
        MarketContext — 包含市场阶段、风险等级、建议仓位、候选标的
    """
    s = Stoke()  # 默认 StokeCached（带缓存）
    ctx = MarketContext()
    ctx.trade_date = datetime.now().date()
    ctx.last_update = datetime.now().isoformat()

    # 1. 盘前预热（传裸 Stoke，避免缓存回环）
    logger.info("===== Step 1/4: 盘前预热 =====")
    s.store.warmup(s._s)

    # 2. 时机判断（大脑）
    logger.info("===== Step 2/4: 时机评估 =====")
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
    logger.info("===== Step 3/4: 发现候选 =====")
    discovery = Discovery(s, ctx)
    discovery.scan()
    logger.info("候选标的: %d 只", len(ctx.candidates))

    logger.info("===== 每日流程完成 =====")
    return ctx
