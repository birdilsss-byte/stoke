"""
ThsSource — 同花顺机构一致预期 EPS

数据源: basic.10jqka.com.cn (HTTP, 零鉴权, GBK 编码)
覆盖: 机构一致预期每股收益（EPS）预测

参考: a-stock-data V3.2.4 §2.2
"""

import logging
from io import StringIO
from typing import Optional

import pandas as pd
import requests

from stoke.config import RATE_LIMIT
from stoke.rate_limiter import RateLimiter
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class ThsSource:
    """同花顺机构一致预期 EPS"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=RATE_LIMIT.get("ths", 1.0))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _UA})
        logger.info("ThsSource 初始化完成，限流 %.1fs", self.limiter.interval)

    # ==================== 连通性检查 ====================

    def health_check(self) -> bool:
        """取贵州茅台一致预期，验证连通性"""
        try:
            df = self.get_eps_forecast("600519")
            ok = not df.empty
            logger.info("ThsSource 健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("ThsSource 健康检查失败: %s", e)
            return False

    # ==================== 一致预期 EPS ====================

    @retry_on_failure(retry_on_empty=True)
    def get_eps_forecast(self, symbol: str) -> pd.DataFrame:
        """
        同花顺个股机构一致预期 EPS。

        直连 basic.10jqka.com.cn，解析 HTML 表格。

        Args:
            symbol: 6 位股票代码，如 '600519'

        Returns:
            DataFrame 列:
            forecast_year  -- 预测年度（如 2026）
            analyst_count  -- 预测机构数
            eps_low        -- EPS 最低预测
            eps_mean       -- EPS 均值（机构一致预期）
            eps_high       -- EPS 最高预测
        """
        self.limiter.wait()
        url = f"https://basic.10jqka.com.cn/new/{symbol}/worth.html"
        logger.info("获取一致预期: %s", symbol)
        try:
            r = self._session.get(url, timeout=15,
                                  headers={"Referer": "https://basic.10jqka.com.cn/"})
            if r.status_code != 200:
                logger.warning("一致预期 HTTP %d: %s", r.status_code, symbol)
                return pd.DataFrame()
            r.encoding = "gbk"
            dfs = pd.read_html(StringIO(r.text))
            raw = pd.DataFrame()
            for df in dfs:
                cols_str = [str(c) for c in df.columns]
                if any("每股收益" in c or "均值" in c for c in cols_str):
                    raw = df
                    break
            if raw.empty and dfs:
                raw = dfs[0]
            if raw.empty:
                return pd.DataFrame()

            # 统一列名为英文
            col_map = {
                "年度": "forecast_year",
                "预测机构数": "analyst_count",
                "最小值": "eps_low",
                "均值": "eps_mean",
                "最大值": "eps_high",
            }
            raw = raw.rename(columns=col_map)
            keep = [c for c in col_map.values() if c in raw.columns]
            raw = raw[keep]
            logger.info("一致预期: %s %d 行", symbol, len(raw))
            return raw
        except Exception as e:
            logger.warning("一致预期解析失败 %s: %s", symbol, e)
            return pd.DataFrame()
