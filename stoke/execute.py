"""
模拟执行层 — 用实时行情跑模拟盘

从 Stoke 数据层拉取实时/最新行情，按当前价模拟成交。
不下单到券商，所有订单记录到 SQLite。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """订单"""
    symbol: str
    name: str
    direction: str          # buy / sell
    quantity: int
    price: float
    strategy_name: str
    reason: str = ""
    status: str = "pending"  # pending / filled / cancelled
    create_date: str = ""
    fill_date: str = ""


class Executor:
    """模拟盘执行器，用实时行情成交"""

    def __init__(self, s: "Stoke", ctx: "MarketContext"):
        self._s = s
        self._ctx = ctx
        self._cash = 100_000  # 虚拟资金

    def place(self, candidate: dict, strategy_name: str) -> Optional[Order]:
        """
        对候选标的生成买入订单

        Args:
            candidate: {"symbol", "name", "score", ...}
            strategy_name: 哪个策略触发

        Returns:
            Order 或 None（资金不足/无行情时）
        """
        symbol = candidate.get("symbol", "")
        name = candidate.get("name", "")

        # 拿实时行情，取当前价
        try:
            rt = self._s.mootdx.get_realtime([symbol])
            if rt is None or rt.empty:
                logger.warning("无实时行情: %s", symbol)
                return None
            price = float(rt.iloc[0]["price"])
        except Exception as e:
            logger.warning("获取实时行情失败 %s: %s", symbol, e)
            return None

        if price <= 0:
            return None

        # 按 ctx.position_advice 和 top-3 等分算仓位
        position_pct = self._ctx.position_advice / 3  # 最多 3 只，等分
        alloc = self._cash * position_pct
        quantity = int(alloc / price / 100) * 100  # 取整百股

        if quantity < 100:
            logger.info("资金不足: %s 需 %d 股", symbol, quantity)
            return None

        cost = price * quantity
        if cost > self._cash:
            logger.info("余额不足: %s 需 %.0f 剩余 %.0f", symbol, cost, self._cash)
            return None

        self._cash -= cost

        order = Order(
            symbol=symbol, name=name, direction="buy",
            quantity=quantity, price=price,
            strategy_name=strategy_name,
            reason=candidate.get("reason", ""),
            create_date=datetime.now().isoformat(),
        )
        logger.info("模拟下单: %s %s %d股 @%.2f [%s]",
                     "买入", symbol, quantity, price, strategy_name)
        return order

    def check_stop(self, positions: list) -> list[Order]:
        """检查止损止盈，生成卖出订单"""
        orders = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            cost = pos.get("cost", 0)
            try:
                rt = self._s.mootdx.get_realtime([symbol])
                if rt is None or rt.empty:
                    continue
                current = float(rt.iloc[0]["price"])
            except Exception:
                continue

            change = (current - cost) / cost
            stop_loss = self._ctx.stop_loss_ratio

            if change <= -stop_loss:
                orders.append(Order(
                    symbol=symbol, name=pos.get("name", ""),
                    direction="sell", quantity=pos.get("quantity", 0),
                    price=current, strategy_name=pos.get("strategy_name", ""),
                    reason=f"止损 ({change*100:.1f}%)",
                    create_date=datetime.now().isoformat(),
                ))
            elif change >= 0.15:
                orders.append(Order(
                    symbol=symbol, name=pos.get("name", ""),
                    direction="sell", quantity=pos.get("quantity", 0),
                    price=current, strategy_name=pos.get("strategy_name", ""),
                    reason=f"止盈 ({change*100:.1f}%)",
                    create_date=datetime.now().isoformat(),
                ))

        return orders
