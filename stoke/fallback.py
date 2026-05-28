"""
FallbackStoke — 带多源自动备份的 Stoke 包装器

当主数据源不可用时，自动按优先级尝试备用源。
零修改现有代码，作为独立可选入口使用。

用法::
    from stoke.fallback import FallbackStoke
    s = FallbackStoke()
    df = s.kline("000001")    # mootdx → efinance → baostock
"""

import logging
from typing import Optional, List

import pandas as pd

from stoke.client_cached import StokeCached
from stoke.exceptions import DataEmptyError

logger = logging.getLogger(__name__)


class FallbackStoke:
    """
    带多源自动备份的 Stoke 包装器

    各方法的 fallback 链：
      - kline:      mootdx → efinance → baostock
      - realtime:   mootdx → efinance
      - stock_list: mootdx → baostock
      - 其余方法直接透传 StokeCached
    """

    def __init__(self, stoke: Optional[StokeCached] = None):
        self._s = stoke or StokeCached()
        logger.info("FallbackStoke 初始化完成（kline/realtime/stock_list 带备份）")

    def _fallback_call(self, name: str, fns: list) -> pd.DataFrame:
        """
        按优先级尝试多个数据源，全部失败时抛出 DataEmptyError

        Args:
            name: 方法名（仅用于日志）
            fns: 数据源函数列表，按优先级从高到低排列
        """
        last_exc = None
        for level, fn in enumerate(fns):
            try:
                result = fn()
                if isinstance(result, pd.DataFrame) and not result.empty:
                    if level > 0:
                        logger.info(
                            "%s: 主源不可用，已从第 %d 级备用源返回", name, level
                        )
                    return result
                if isinstance(result, pd.DataFrame):
                    logger.warning(
                        "%s: 第 %d 级源返回空数据", name, level
                    )
            except Exception as e:
                last_exc = e
                logger.warning(
                    "%s: 第 %d 级源失败 (%s: %s)", name, level,
                    type(e).__name__, e,
                )
        raise DataEmptyError(
            f"{name}: 所有数据源均不可用"
        ) from last_exc

    # ==================== kline（3 级备份） ====================

    def kline(
        self,
        symbol: str,
        frequency: int = 9,
        start: int = 0,
        offset: int = 800,
    ) -> pd.DataFrame:
        """
        日 K 线：mootdx → efinance → baostock

        Args:
            symbol: 股票代码，如 '000001'
            frequency: K 线周期，9=日线（仅日线有备份）
            start: 起始位置
            offset: 获取条数
        """
        if frequency != 9:
            return self._s.kline(symbol, frequency, start, offset)

        return self._fallback_call("kline", [
            # Level 0: mootdx（主源，TCP 通达信）
            lambda: self._s.kline(symbol, frequency, start, offset),
            # Level 1: efinance（极速，~0.3s）
            lambda: self._s.kline_efinance(symbol),
            # Level 2: baostock（含复权）
            lambda: self._s.baostock.get_kline(
                f"sh.{symbol}" if symbol.startswith("6") else f"sz.{symbol}",
                frequency="d",
            ),
        ])

    # ==================== 实时行情（2 级备份） ====================

    def realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        实时行情：mootdx → efinance

        Args:
            symbols: 股票代码列表
        """
        return self._fallback_call("realtime", [
            lambda: self._s.realtime(symbols),
            lambda: self._s.efinance.get_realtime(symbols),
        ])

    # ==================== 股票列表（3 级备份） ====================

    def stock_list(self) -> pd.DataFrame:
        """
        全市场股票列表：mootdx → baostock → zhitu
        """
        return self._fallback_call("stock_list", [
            lambda: self._s.stock_list(),
            lambda: self._s.all_stock(),
            lambda: self._s.zhitu_stock_list(),
        ])

    # ==================== 透传 StokeCached ====================

    def __getattr__(self, name):
        """未覆盖的方法直接透传到 StokeCached"""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._s, name)
