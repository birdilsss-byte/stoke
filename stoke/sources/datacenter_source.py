"""
DatacenterSource — 东财数据中心龙虎榜

数据源: datacenter-web.eastmoney.com (HTTP, 零鉴权)
覆盖: 龙虎榜席位明细 + 全市场龙虎榜

限流: 共享 eastmoney_source 的 _em_rate_limit() 全局限流

参考: a-stock-data V3.2.4 §3.5
"""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from stoke.config import RATE_LIMIT
from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure
from stoke.sources.eastmoney_source import _em_rate_limit, EM_SESSION

logger = logging.getLogger(__name__)

_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


class DatacenterSource:
    """东方财富数据中心 — 龙虎榜数据"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("datacenter", 1.5))
        logger.info("DatacenterSource 初始化完成，限流 %.1fs", self.limiter.interval)

    # ==================== 连通性检查 ====================

    def health_check(self) -> bool:
        """取最近交易日龙虎榜（1 条即可），验证连通性"""
        try:
            yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            df = self.get_full_market_billboard(yesterday)
            ok = not df.empty
            logger.info("Datacenter 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("Datacenter 健康检查失败: %s", e)
            return False

    # ==================== 内部通用查询 ====================

    def _datacenter_query(self, report_name: str, filter_str: str = "",
                          columns: str = "ALL", page_size: int = 100,
                          sort_columns: str = "", sort_types: str = "") -> list:
        """
        东财数据中心通用查询。

        Args:
            report_name: 报表名，如 RPT_DAILYBILLBOARD_DETAILSNEW
            filter_str: SQL 风格过滤条件
            columns: 返回列，ALL 全部
            page_size: 每页条数
            sort_columns: 排序列
            sort_types: 排序方向（-1 降序）

        Returns:
            list[dict] 数据行列表
        """
        params = {
            "reportName": report_name, "columns": columns,
            "filter": filter_str,
            "pageNumber": "1", "pageSize": str(page_size),
            "sortColumns": sort_columns, "sortTypes": sort_types,
            "source": "WEB", "client": "WEB",
        }
        _em_rate_limit()
        r = EM_SESSION.get(
            _DATACENTER_URL, params=params, timeout=15,
            headers={"Referer": "https://data.eastmoney.com/"},
        )
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
        return []

    # ==================== 龙虎榜席位明细 ====================

    @retry_on_failure()
    def get_billboard_seat_detail(self, code: str,
                                  start_date: str,
                                  end_date: str) -> pd.DataFrame:
        """
        龙虎榜营业部席位明细（个股维度）。

        Args:
            code: 6 位股票代码
            start_date: 起始日期 YYYY-MM-DD
            end_date: 截止日期 YYYY-MM-DD

        Returns:
            DataFrame 列:
            TRADE_DATE         -- 交易日期
            SECURITY_CODE      -- 股票代码
            SECURITY_NAME_ABBR -- 股票简称
            BILLBOARD_NET_AMT  -- 龙虎榜净买入金额
            CHANGE_PCT         -- 涨跌幅 (%)
            TURNOVERRATE       -- 换手率 (%)
            TOTAL_EXPLAIN      -- 上榜原因
        """
        self.limiter.wait()
        filter_str = (
            f"(TRADE_DATE>='{start_date}')"
            f"(TRADE_DATE<='{end_date}')"
            f"(SECURITY_CODE=\"{code}\")"
        )
        logger.info("获取龙虎榜席位: %s [%s, %s]", code, start_date, end_date)
        data = self._datacenter_query(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=filter_str,
            sort_columns="TRADE_DATE", sort_types="-1",
        )
        df = pd.DataFrame(data) if data else pd.DataFrame()
        logger.info("龙虎榜席位: %s %d 条", code, len(df))
        return df

    # ==================== 全市场龙虎榜 ====================

    @retry_on_failure()
    def get_full_market_billboard(self, date_str: str) -> pd.DataFrame:
        """
        全市场龙虎榜每日汇总。

        Args:
            date_str: 日期 YYYY-MM-DD

        Returns:
            DataFrame 列:
            TRADE_DATE         -- 交易日期
            SECURITY_CODE      -- 股票代码
            SECURITY_NAME_ABBR -- 股票简称
            BILLBOARD_NET_AMT  -- 净买入金额
            CHANGE_PCT         -- 涨跌幅 (%)
            TURNOVERRATE       -- 换手率 (%)
            TOTAL_EXPLAIN      -- 上榜原因
            EXCEED_PCT         -- 偏离值
        """
        self.limiter.wait()
        filter_str = f"(TRADE_DATE='{date_str}')"
        logger.info("获取全市场龙虎榜: %s", date_str)
        data = self._datacenter_query(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=filter_str,
            sort_columns="BILLBOARD_NET_AMT", sort_types="-1",
        )
        df = pd.DataFrame(data) if data else pd.DataFrame()
        logger.info("全市场龙虎榜: %s %d 条", date_str, len(df))
        return df
