"""
沉淀层 — 记录模拟交易、按策略维度统计、生成对比报告

两张表：
  trades — 每笔交易明细（开仓+平仓）
  strategy_snapshots — 每日策略表现快照
"""

import logging
import sqlite3
from datetime import datetime, date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class Journal:
    """交易日志与策略统计"""

    def __init__(self, store: "Store"):
        self._store = store

    # ===== 交易记录 =====

    def log_trade(self, trade_dict: dict):
        """记录一笔成交"""
        now = datetime.now().isoformat()
        with sqlite3.connect(self._store.db_path) as conn:
            conn.execute(
                """INSERT INTO trades
                   (symbol, name, direction, quantity, price, strategy_name,
                    order_date, fill_date, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade_dict.get("symbol", ""),
                    trade_dict.get("name", ""),
                    trade_dict.get("direction", "buy"),
                    trade_dict.get("quantity", 0),
                    trade_dict.get("price", 0),
                    trade_dict.get("strategy_name", ""),
                    trade_dict.get("create_date") or now,
                    now,
                    trade_dict.get("reason", ""),
                ),
            )
        logger.debug("交易记录: %s %s", trade_dict.get("direction"),
                      trade_dict.get("symbol"))

    def log_exit(self, symbol: str, exit_price: float,
                 exit_date: Optional[str] = None):
        """更新最近一笔该标的买入的止盈/止损价"""
        edate = exit_date or datetime.now().isoformat()
        with sqlite3.connect(self._store.db_path) as conn:
            # 找该标的最新买入
            row = conn.execute(
                """SELECT id, price, order_date FROM trades
                   WHERE symbol = ? AND direction = 'buy' AND exit_price IS NULL
                   ORDER BY order_date DESC LIMIT 1""",
                (symbol,),
            ).fetchone()
            if row:
                trade_id, buy_price, buy_date = row
                pnl = (exit_price / buy_price - 1) * 100
                hold_days = (datetime.fromisoformat(edate[:10])
                             - datetime.fromisoformat(buy_date[:10])).days
                conn.execute(
                    """UPDATE trades
                       SET exit_price = ?, exit_date = ?, pnl_pct = ?,
                           max_hold_days = ?
                       WHERE id = ?""",
                    (exit_price, edate, round(pnl, 2), hold_days, trade_id),
                )
                logger.info("平仓: %s @%.2f %.2f%%", symbol, exit_price, pnl)

    # ===== 策略快照 =====

    def snapshot(self, strategy_name: str, result):
        """保存当日策略表现快照"""
        today = date.today().isoformat()
        with sqlite3.connect(self._store.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO strategy_snapshots
                   (date, strategy_name, total_return, sharpe,
                    max_drawdown, win_rate, trade_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    today, strategy_name,
                    getattr(result, "total_return", 0),
                    getattr(result, "sharpe", 0),
                    getattr(result, "max_drawdown", 0),
                    getattr(result, "win_rate", 0),
                    getattr(result, "trade_count", 0),
                ),
            )
        logger.debug("快照: %s @ %s", strategy_name, today)

    # ===== 统计对比 =====

    def compare_strategies(self) -> pd.DataFrame:
        """策略对比表（最新快照）"""
        import sqlite3
        with sqlite3.connect(self._store.db_path) as conn:
            df = pd.read_sql(
                """SELECT strategy_name, total_return, sharpe, max_drawdown,
                          win_rate, trade_count
                   FROM strategy_snapshots
                   WHERE date = (SELECT MAX(date) FROM strategy_snapshots)""",
                conn,
            )
        return df

    def weekly_report(self) -> str:
        """生成 Markdown 周报"""
        import sqlite3
        lines = ["# Stoke 模拟盘周报", "",
                  f"生成时间: {datetime.now().isoformat()}", ""]
        with sqlite3.connect(self._store.db_path) as conn:
            # 本周交易
            week_ago = (date.today() - pd.Timedelta(days=7)).isoformat()
            trades = pd.read_sql(
                """SELECT * FROM trades WHERE order_date >= ?""",
                conn, params=(week_ago,),
            )
            lines.append("## 本周交易")
            lines.append(f"共 {len(trades)} 笔")
            if not trades.empty:
                lines.append(trades[["symbol", "direction", "price",
                                      "strategy_name", "pnl_pct"]].to_markdown(index=False))
            lines.append("")

            # 策略对比
            df = self.compare_strategies()
            if not df.empty:
                lines.append("## 策略对比")
                lines.append(df.to_markdown(index=False))

        return "\n".join(lines)
