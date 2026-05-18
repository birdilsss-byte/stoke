"""
mootdx 数据源 — 通达信 TCP 协议

零鉴权，TCP 连接稳定不封 IP。
提供：K 线、实时行情（含 5 档盘口）、股票列表、F10 财务快照。

默认不限流（已内置间隔控制到 0）。
"""

from typing import Optional, List

import pandas as pd
from mootdx.quotes import Quotes

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT


class MootdxSource:
    """通达信数据源，TCP 协议，零鉴权"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: 可选，默认不限流
        """
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT["mootdx"])
        self._client: Optional[Quotes] = None

    @property
    def client(self) -> Quotes:
        """延迟初始化，首次调用时才连接"""
        if self._client is None:
            self._client = Quotes.factory(market="std")
        return self._client

    def health_check(self) -> bool:
        """连通性检查：取一只股票 K 线，成功返回 True"""
        try:
            data = self.client.bars(symbol="000001", frequency=9, start=0, offset=1)
            return len(data) > 0
        except Exception:
            return False

    # ---------- K 线 ----------

    def get_kline(
        self,
        symbol: str,
        frequency: int = 9,
        start: int = 0,
        offset: int = 800,
    ) -> pd.DataFrame:
        """
        获取日 K 线数据

        Args:
            symbol: 股票代码，如 '000001'（深市）或 '600000'（沪市）
            frequency: K 线周期，9=日线，7=周线，6=月线
            start: 起始位置（0=最新）
            offset: 获取条数，默认 800

        Returns:
            DataFrame，含 open、close、high、low、volume、datetime 等列
        """
        self.limiter.wait()
        return self.client.bars(
            symbol=symbol,
            frequency=frequency,
            start=start,
            offset=offset,
        )

    # ---------- 实时行情 ----------

    def get_realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取实时行情，含 5 档买卖盘口

        Args:
            symbols: 股票代码列表，如 ['000001', '600000', '000858']

        Returns:
            DataFrame，46 个字段：
            code、price、open、high、low、vol、amount、last_close、
            bid1~5、ask1~5、bid_vol1~5、ask_vol1~5 等
        """
        self.limiter.wait()
        return self.client.quotes(symbol=symbols)

    # ---------- 股票列表 ----------

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全市场股票列表（27046 只）

        Returns:
            DataFrame，含 code、name、volunit、decimal_point、pre_close 列
        """
        self.limiter.wait()
        return self.client.stocks()

    # ---------- F10 基础数据 ----------

    def get_f10(self, symbol: str) -> Optional[dict]:
        """
        获取 F10 财务快照（37 字段 + 9 大类文本资料）

        ⚠️ 当前版本与 pandas 3.0 有兼容性问题，
        某些字段可能返回 DataFrame 而非预期类型。

        Args:
            symbol: 股票代码

        Returns:
            dict 或 None
        """
        self.limiter.wait()
        try:
            result = self.client.finance(symbol=symbol)
            return result
        except Exception:
            return None
