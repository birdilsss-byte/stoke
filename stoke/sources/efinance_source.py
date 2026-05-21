"""
efinance 数据源 — 整合新浪/网易/东方财富公开接口

零 API Key、零注册、零付费，无调用次数限制（合理频率）。
返回标准 DataFrame，内置重试机制。

优势：
  - K 线极速（~0.3s），比 akshare 快 15 倍
  - 龙虎榜数据更详细（含净买额/上榜原因）
  - 独有：十大股东、股东人数、公司基本信息
  - 覆盖龙虎榜/基金/可转债（akshare 覆盖不全的部分）

限制：实时延迟 15 秒（非 Level-2 实时行情）
"""

import logging
from typing import Optional

import efinance as ef
import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)


class EFinanceSource:
    """efinance 数据源，零限制极速接口"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=0.5)
        logger.info("EFinanceSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def health_check(self) -> bool:
        """连通性检查：获取龙虎榜（接口轻量稳定）"""
        try:
            df = ef.stock.get_daily_billboard()
            ok = len(df) > 0
            logger.info("EFinance 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("EFinance 健康检查失败: %s", e)
            return False

    # ---------- K 线（极速，替代 akshare） ----------

    @retry_on_failure()
    def get_kline(
        self,
        symbol: str,
        start_date: str = "20250101",
        end_date: str = "",
    ) -> pd.DataFrame:
        """
        获取历史日 K 线（极速 ~0.3s）

        Args:
            symbol: 6 位股票代码，如 '600519'
            start_date: 起始日期 YYYYMMDD
            end_date: 截止日期 YYYYMMDD，默认今天

        Returns:
            DataFrame，含 股票名称、股票代码、日期、开盘、收盘、最高、
            最低、成交量、成交额、振幅、涨跌幅、涨跌额、换手率
        """
        self.limiter.wait()
        from datetime import date
        if not end_date:
            end_date = date.today().strftime("%Y%m%d")
        logger.info("EFinance K 线: %s (%s ~ %s)", symbol, start_date, end_date)
        return ef.stock.get_quote_history(
            symbol, beg=start_date, end=end_date,
        )

    # ---------- 龙虎榜（补充 akshare） ----------

    @retry_on_failure()
    def get_daily_billboard(self) -> pd.DataFrame:
        """
        今日龙虎榜（含净买额/上榜原因，比 akshare 更详细）

        Returns:
            DataFrame，含 代码、名称、涨跌幅、收盘价、龙虎榜净买额、
            成交额、上榜原因、营业部明细 等列
        """
        self.limiter.wait()
        logger.info("EFinance 龙虎榜")
        return ef.stock.get_daily_billboard()

    # ---------- 十大股东（独有） ----------

    @retry_on_failure()
    def get_top10_holders(self, symbol: str) -> pd.DataFrame:
        """
        十大股东信息（efinance 独有）

        Args:
            symbol: 6 位股票代码，如 '600519'

        Returns:
            DataFrame，含 股东名称、持股数、持股比例、增减、变动率 等列
        """
        self.limiter.wait()
        logger.info("EFinance 十大股东: %s", symbol)
        return ef.stock.get_top10_stock_holder_info(symbol)

    # ---------- 股东人数（独有） ----------

    @retry_on_failure()
    def get_holder_number(self, symbol: str) -> pd.DataFrame:
        """
        股东人数变化趋势（efinance 独有）

        Args:
            symbol: 6 位股票代码

        Returns:
            DataFrame，含 日期、股东人数、变化 等列
        """
        self.limiter.wait()
        logger.info("EFinance 股东人数: %s", symbol)
        return ef.stock.get_latest_holder_number(symbol)

    # ---------- 公司基本信息（独有） ----------

    @retry_on_failure()
    def get_company_info(self, symbol: str) -> pd.DataFrame:
        """
        公司基本信息（efinance 独有）

        Args:
            symbol: 6 位股票代码

        Returns:
            DataFrame，含 公司名称、所属行业、上市日期、总股本、流通股 等列
        """
        self.limiter.wait()
        logger.info("EFinance 公司信息: %s", symbol)
        return ef.stock.get_base_info(symbol)

    # ---------- 实时行情（备用） ----------

    @retry_on_failure()
    def get_realtime(self, symbols: Optional[list] = None) -> pd.DataFrame:
        """
        实时行情快照（延迟 ~15 秒，备用）

        Args:
            symbols: 股票代码列表，默认全市场

        Returns:
            DataFrame，含 代码、名称、最新价、涨跌幅、成交量、成交额 等列
        """
        self.limiter.wait()
        logger.info("EFinance 实时行情: %d 只", len(symbols) if symbols else 0)
        return ef.stock.get_realtime_quotes(symbols)
