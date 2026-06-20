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
        '均值' 列即机构一致预期 EPS。

        Args:
            symbol: 6 位股票代码，如 '600519'

        Returns:
            DataFrame（列名为中文，由 pd.read_html 自动推断，通常包含：
            预测年度、日期、每股收益(均值/最高/最低)、预测机构数、行业）
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
            for df in dfs:
                cols_str = [str(c) for c in df.columns]
                if any("每股收益" in c or "均值" in c for c in cols_str):
                    logger.info("一致预期: %s %d 行", symbol, len(df))
                    return df
            # fallback: 返回第一个非空表
            if dfs:
                logger.info("一致预期: %s 返回第 1 个表格 (%d 行)", symbol, len(dfs[0]))
                return dfs[0]
            return pd.DataFrame()
        except Exception as e:
            logger.warning("一致预期解析失败 %s: %s", symbol, e)
            return pd.DataFrame()
