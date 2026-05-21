"""
mootdx 数据源 — 通达信 TCP 协议

零鉴权，TCP 连接稳定不封 IP。
提供：K 线、实时行情（含 5 档盘口）、股票列表、F10 财务快照。

遇到连接断开时会自动重连一次，无需手动干预。
默认不限流（已内置间隔控制到 0）。
"""

import logging
from typing import Optional, List

import pandas as pd
from mootdx.quotes import Quotes

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.exceptions import SourceNotReadyError

logger = logging.getLogger(__name__)


class MootdxSource:
    """通达信数据源，TCP 协议，零鉴权"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: 可选，默认不限流
        """
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT["mootdx"])
        self._client: Optional[Quotes] = None
        logger.info("MootdxSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    @property
    def client(self) -> Quotes:
        """延迟初始化，首次调用时才连接"""
        if self._client is None:
            self._client = Quotes.factory(market="std")
            logger.debug("mootdx 客户端已创建")
        return self._client

    def _call(self, method_name: str, method, *args, **kwargs):
        """
        调用客户端方法，失败时自动重连一次。

        Args:
            method_name: 方法名（仅用于日志）
            method: 要调用的可执行对象
        """
        for attempt in range(2):
            try:
                return method(*args, **kwargs)
            except Exception as e:
                if attempt == 0:
                    logger.warning("mootdx %s 失败，尝试重连: %s", method_name, e)
                    self._client = None  # 断开旧连接
                    _ = self.client  # 触发重连
                else:
                    logger.error("mootdx %s 重连后仍然失败: %s", method_name, e)
                    raise

    def health_check(self) -> bool:
        """连通性检查：取一只股票 K 线，成功返回 True"""
        try:
            data = self.client.bars(symbol="000001", frequency=9, start=0, offset=1)
            ok = len(data) > 0
            logger.info("健康检查 %s", "通过" if ok else "失败(数据为空)")
            return ok
        except Exception as e:
            logger.warning("健康检查失败: %s", e)
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
        logger.info("获取 K 线: %s (frequency=%d, offset=%d)", symbol, frequency, offset)
        return self._call(
            "get_kline",
            self.client.bars,
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
        logger.info("获取实时行情: %d 只", len(symbols))
        return self._call(
            "get_realtime",
            self.client.quotes,
            symbol=symbols,
        )

    # ---------- 股票列表 ----------

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取全市场股票列表（27046 只）

        Returns:
            DataFrame，含 code、name、volunit、decimal_point、pre_close 列
        """
        self.limiter.wait()
        logger.info("获取全市场股票列表")
        return self._call("get_stock_list", self.client.stocks)

    # ---------- F10 基础数据 ----------

    def get_f10(self, symbol: str) -> Optional[dict]:
        """
        获取 F10 财务快照（37 字段 + 9 大类文本资料）

        ⚠️ 当前版本与 pandas 3.0 有兼容性问题，
        某些字段可能返回 DataFrame 而非预期类型。

        Args:
            symbol: 股票代码

        Returns:
            dict 或 None（该股票无 F10 数据时返回 None）
        """
        self.limiter.wait()
        logger.info("获取 F10: %s", symbol)
        try:
            result = self._call("get_f10", self.client.finance, symbol=symbol)
            return result
        except Exception as e:
            logger.error("获取 F10 失败 %s: %s", symbol, e)
            return None

    # ---------- 板块数据 ----------

    def get_sector_members(self, sector_name: str) -> pd.DataFrame:
        """
        获取板块/指数成分股列表

        数据来源：通达信 block 数据库，含所有板块/指数的成分股关系。
        用 blockname 过滤，如需获取行业板块成分股名称，先通过 akshare
        的 get_sector_rank() 获取板块名称列表。

        Args:
            sector_name: 板块名称，如 '沪深300'、'精选指数'

        Returns:
            DataFrame，含 blockname、block_type、code_index、code 等列
        """
        self.limiter.wait()
        logger.info("获取板块成分股: %s", sector_name)
        blocks = self._call("get_sector_members", self.client.block)
        result = blocks[blocks['blockname'] == sector_name].copy()
        logger.info("板块 %s: 共 %d 只成分股", sector_name, len(result))
        return result
