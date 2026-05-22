"""
全局上下文 — 各层之间共享的市场状态快照

时机层写入，发现层读取，不上锁不排队（单进程无并发问题）。
用 dataclass 而不是 dict：IDE 有自动补全和类型检查。
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class MarketContext:
    """各层之间共享的市场状态快照"""

    # ===== 时机层输出 → 发现层/执行层消费 =====

    market_phase: str = "未知"          # "上升" / "下降" / "震荡"
    risk_level: int = 5                  # 1-10，越高越危险
    position_advice: float = 0.3         # 建议仓位比例 0-1
    stop_loss_ratio: float = 0.05        # 建议止损比例

    # 五维权重分解
    market_weight: float = 0.0           # 大盘维度
    valuation_weight: float = 0.0        # 估值维度
    sector_weight: float = 0.0           # 行业维度
    sentiment_weight: float = 0.0        # 情绪维度
    fund_flow_weight: float = 0.0        # 资金流维度

    # ===== 发现层输出 → 时机层/执行层消费 =====

    candidates: list = field(default_factory=list)      # [{symbol, name, score, reason}]
    watch_list: list = field(default_factory=list)      # [{symbol, name, alert_price}]

    # ===== 执行层/沉淀层消费 =====

    positions: list = field(default_factory=list)       # [{symbol, quantity, cost, strategy_name}]
    active_strategies: dict = field(default_factory=dict)  # {name: strategy_fn}

    # ===== 元信息 =====

    trade_date: Optional[date] = None
    last_update: str = ""
