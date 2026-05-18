"""
腾讯财经数据源 — 通过 akshare 的 lg 接口获取估值数据

提供：指数 PE 历史、全市场 PB 历史。
默认 3 秒间隔，自带自动重试（网络抖动时最多重试 3 次）。
"""

import logging
from typing import Optional

import akshare as ak
import pandas as pd

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)


class TencentSource:
    """腾讯财经估值数据源"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        """
        Args:
            rate_limiter: 可选，默认 3 秒间隔
        """
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT["tencent"])
        logger.info("TencentSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def health_check(self) -> bool:
        """连通性检查：获取全市场 PB（接口轻量）"""
        try:
            data = ak.stock_a_all_pb()
            ok = len(data) > 0
            logger.info("健康检查 %s", "通过" if ok else "失败(数据为空)")
            return ok
        except Exception as e:
            logger.warning("健康检查失败: %s", e)
            return False

    # ---------- 指数 PE ----------

    @retry_on_failure()
    def get_index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        """
        获取指数 PE（市盈率）历史

        Args:
            index_name: 指数名称，如 "上证50"、"沪深300"、"上证A股"

        Returns:
            DataFrame，含 日期、指数点位、静态市盈率、滚动市盈率、
            等权静态市盈率、等权滚动市盈率、市盈率中位数 等列
        """
        self.limiter.wait()
        logger.info("获取指数 PE: %s", index_name)
        return ak.stock_index_pe_lg(symbol=index_name)

    # ---------- 全市场 PB ----------

    @retry_on_failure()
    def get_market_pb(self) -> pd.DataFrame:
        """
        获取全市场 PB（市净率）历史

        Returns:
            DataFrame，含 date、middlePB、equalWeightAveragePB、close、
            以及各种分位数信息
        """
        self.limiter.wait()
        logger.info("获取全市场 PB")
        return ak.stock_a_all_pb()
