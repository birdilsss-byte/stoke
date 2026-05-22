"""
经验回测层 — 轻量向量化回测引擎

不走事件驱动，直接遍历历史 K 线，记录信号→开仓→止损止盈→平仓。
支持多策略并行对比：一次跑 N 个策略，横向比较收益/夏普/回撤。
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ==================== 数据结构 ====================

@dataclass
class Signal:
    """策略信号"""
    symbol: str
    direction: str          # "buy" / "sell"
    price: float
    reason: str
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    strategy_name: str
    total_return: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    avg_hold_days: float = 0.0
    trades: list = field(default_factory=list)


# ==================== 内置策略 ====================

def ma_cross(symbol: str, df: pd.DataFrame, ctx=None) -> Optional[Signal]:
    """5/20 日均线金叉买入，死叉卖出"""
    if len(df) < 20:
        return None
    ma5 = df["close"].rolling(5).mean()
    ma20 = df["close"].rolling(20).mean()
    # 金叉：MA5 上穿 MA20
    if ma5.iloc[-2] <= ma20.iloc[-2] and ma5.iloc[-1] > ma20.iloc[-1]:
        price = df["close"].iloc[-1]
        return Signal(
            symbol=symbol, direction="buy", price=price,
            reason="MA5 上穿 MA20",
            stop_loss=price * 0.95, take_profit=price * 1.15,
        )
    # 死叉：MA5 下穿 MA20
    if ma5.iloc[-2] >= ma20.iloc[-2] and ma5.iloc[-1] < ma20.iloc[-1]:
        return Signal(
            symbol=symbol, direction="sell", price=df["close"].iloc[-1],
            reason="MA5 下穿 MA20",
        )
    return None


def breakout(symbol: str, df: pd.DataFrame, ctx=None) -> Optional[Signal]:
    """突破 20 日高点买入，跌破 10 日低点卖出"""
    if len(df) < 20:
        return None
    high_20 = df["high"].rolling(20).max().iloc[-2]
    low_10 = df["low"].rolling(10).min().iloc[-2]
    close = df["close"].iloc[-1]
    if close > high_20:
        return Signal(
            symbol=symbol, direction="buy", price=close,
            reason=f"突破 20 日高点 {high_20:.2f}",
            stop_loss=low_10, take_profit=close * 1.15,
        )
    if close < low_10:
        return Signal(
            symbol=symbol, direction="sell", price=close,
            reason=f"跌破 10 日低点 {low_10:.2f}",
        )
    return None


def volume_surge(symbol: str, df: pd.DataFrame, ctx=None) -> Optional[Signal]:
    """放量上涨：成交量 > 1.5 倍 20 日均量 且 涨幅 > 3%"""
    if len(df) < 20:
        return None
    avg_vol = df["volume"].rolling(20).mean().iloc[-2]
    vol_today = df["volume"].iloc[-1]
    change_pct = (df["close"].iloc[-1] / df["close"].iloc[-2] - 1)
    if vol_today > 1.5 * avg_vol and change_pct > 0.03:
        price = df["close"].iloc[-1]
        return Signal(
            symbol=symbol, direction="buy", price=price,
            reason=f"放量上涨 {change_pct*100:.1f}%",
            stop_loss=price * 0.95, take_profit=price * 1.10,
        )
    return None


def macd(symbol: str, df: pd.DataFrame, ctx=None) -> Optional[Signal]:
    """MACD 金叉死叉：DIF 上穿 DEA 买入，下穿卖出"""
    if len(df) < 35:
        return None
    close = df["close"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    # 金叉
    if dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
        price = close.iloc[-1]
        return Signal(
            symbol=symbol, direction="buy", price=price,
            reason="MACD 金叉",
            stop_loss=price * 0.95, take_profit=price * 1.15,
        )
    # 死叉
    if dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
        price = close.iloc[-1]
        return Signal(
            symbol=symbol, direction="sell", price=price,
            reason="MACD 死叉",
        )
    return None


def weekly_rsi(symbol: str, df: pd.DataFrame, ctx=None) -> Optional[Signal]:
    """周线 RSI 低吸高抛 — RSI(14) < 30 超卖买入，> 70 超买卖出"""
    if len(df) < 20:
        return None
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))

    price = close.iloc[-1]
    # 超卖 → 买入
    if rsi.iloc[-1] < 30:
        return Signal(
            symbol=symbol, direction="buy", price=price,
            reason=f"周线 RSI 超卖 ({rsi.iloc[-1]:.0f})",
            stop_loss=price * 0.93, take_profit=price * 1.20,
        )
    # 超买 → 卖出
    if rsi.iloc[-1] > 70:
        return Signal(
            symbol=symbol, direction="sell", price=price,
            reason=f"周线 RSI 超买 ({rsi.iloc[-1]:.0f})",
        )
    return None


# ==================== 回测引擎 ====================

class Backtester:
    """轻量向量化回测引擎"""

    def __init__(self, s: "Stoke"):
        self._s = s

    def run(
        self,
        strategy_fn: Callable,
        symbols: list,
        start_date: str,
        end_date: str,
        initial_cash: float = 100_000,
        frequency: int = 9,
    ) -> BacktestResult:
        """
        对一批标的跑单个策略

        Args:
            strategy_fn: 策略函数 (symbol, df, ctx) -> Signal | None
            symbols: 股票代码列表
            start_date: 回测起始日 YYYY-MM-DD
            end_date: 回测结束日 YYYY-MM-DD
            initial_cash: 初始资金
            frequency: K 线周期，9=日线，5=周线，6=月线
        """
        result = BacktestResult(strategy_name=strategy_fn.__name__)
        cash = initial_cash
        position = None  # {symbol, buy_price, buy_date, buy_idx, stop_loss, take_profit}

        for symbol in symbols:
            df = self._s.kline(symbol, frequency=frequency)
            if df is None or df.empty or len(df) < 20:
                continue
            # 统一列名：mootdx 裸数据用 datetime，缓存后用 date
            if "datetime" in df.columns and "date" not in df.columns:
                df["date"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
            df = df.sort_values("date").reset_index(drop=True)
            mask = (df["date"] >= start_date) & (df["date"] <= end_date)
            df = df[mask].reset_index(drop=True)
            if len(df) < 20:
                continue

            for i in range(20, len(df)):
                today = df.iloc[:i + 1]
                today_close = df["close"].iloc[i]
                today_date = df["date"].iloc[i]

                # 有持仓：T+1 约束 → 买入当日不能卖出
                if position and position["symbol"] == symbol:
                    if i <= position.get("buy_idx", i):
                        continue
                    if today_close <= position["stop_loss"]:
                        pnl = (today_close / position["buy_price"] - 1) * 100
                        result.trades.append({
                            "symbol": symbol, "buy_date": position["buy_date"],
                            "sell_date": today_date, "buy_price": position["buy_price"],
                            "sell_price": today_close, "pnl_pct": round(pnl, 2),
                            "reason": "止损",
                        })
                        cash = cash * (1 + pnl / 100)
                        position = None
                        continue
                    if today_close >= position["take_profit"]:
                        pnl = (today_close / position["buy_price"] - 1) * 100
                        result.trades.append({
                            "symbol": symbol, "buy_date": position["buy_date"],
                            "sell_date": today_date, "buy_price": position["buy_price"],
                            "sell_price": today_close, "pnl_pct": round(pnl, 2),
                            "reason": "止盈",
                        })
                        cash = cash * (1 + pnl / 100)
                        position = None
                        continue

                # 无持仓：调策略看有没有买入信号
                if position is None:
                    signal = strategy_fn(symbol, today)
                    if signal and signal.direction == "buy":
                        position = {
                            "symbol": symbol,
                            "buy_price": signal.price,
                            "buy_date": today_date,
                            "buy_idx": i,
                            "quantity": 1,
                            "stop_loss": signal.stop_loss,
                            "take_profit": signal.take_profit,
                        }

            # 该标的遍历完，强制平仓
            if position and position["symbol"] == symbol:
                last_close = df["close"].iloc[-1]
                pnl = (last_close / position["buy_price"] - 1) * 100
                result.trades.append({
                    "symbol": symbol, "buy_date": position["buy_date"],
                    "sell_date": df["date"].iloc[-1], "buy_price": position["buy_price"],
                    "sell_price": last_close, "pnl_pct": round(pnl, 2),
                    "reason": "回测结束平仓",
                })
                cash = cash * (1 + pnl / 100)
                position = None

        # 汇总统计
        result.trade_count = len(result.trades)
        if result.trades:
            pnls = [t["pnl_pct"] for t in result.trades]
            wins = [p for p in pnls if p > 0]
            result.win_rate = len(wins) / len(pnls) * 100
            result.total_return = (cash / initial_cash - 1) * 100

            # 夏普（简化：日收益标准差年化）
            if len(pnls) >= 2:
                daily_returns = np.array(pnls) / 100
                mean_ret = np.mean(daily_returns)
                std_ret = np.std(daily_returns, ddof=1)
                result.sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0

            # 最大回撤（累计收益曲线）
            cumulative = np.cumprod([1 + p / 100 for p in pnls])
            peak = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - peak) / peak * 100
            result.max_drawdown = abs(float(np.min(drawdowns)))

        return result

    def compare(
        self,
        strategies: dict,
        symbols: list,
        start_date: str,
        end_date: str,
        frequency: int = 9,
    ) -> pd.DataFrame:
        """并行跑多个策略，返回对比表"""
        rows = []
        for name, fn in strategies.items():
            logger.info("回测: %s ...", name)
            r = self.run(fn, symbols, start_date, end_date, frequency=frequency)
            rows.append({
                "strategy": name,
                "return_%": round(r.total_return, 2),
                "sharpe": round(r.sharpe, 2),
                "max_dd_%": round(r.max_drawdown, 2),
                "win_rate_%": round(r.win_rate, 1),
                "trades": r.trade_count,
            })
        return pd.DataFrame(rows)

    def validate(self, strategy_fn: Callable, symbols: list = None,
                 recent_days: int = 60, min_sharpe: float = 0.5) -> bool:
        """验证策略近期是否有效"""
        from datetime import date, timedelta
        if symbols is None:
            symbols = ["000001", "600519"]
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=recent_days)).isoformat()
        r = self.run(strategy_fn, symbols, start, end)
        return r.total_return > 0 and r.sharpe > min_sharpe
