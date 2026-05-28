"""
腾讯财经直连数据源 — 纯 requests，零 akshare 依赖

端点：
  - qt.gtimg.cn     实时行情（50+ 字段，毫秒级响应）
  - proxy.finance.qq.com  K 线（日/周/月，前/后复权）

免费、零注册、零 API Key。
"""

import logging
import json
import re
from typing import Optional, List
from datetime import datetime

import pandas as pd
import requests

from stoke.rate_limiter import RateLimiter
from stoke.config import RATE_LIMIT
from stoke.utils import retry_on_failure

logger = logging.getLogger(__name__)


class TencentDirectSource:
    """腾讯财经直连数据源 — 实时行情 + K 线"""

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.limiter = rate_limiter or RateLimiter(interval=0.3)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        logger.info("TencentDirectSource 初始化，限流间隔 %.1f 秒", self.limiter.interval)

    def health_check(self) -> bool:
        """连通性检查：获取贵州茅台实时行情"""
        try:
            r = self._session.get(
                "http://qt.gtimg.cn/q=sh600519",
                timeout=5,
            )
            ok = r.status_code == 200 and "600519" in r.text
            logger.info("腾讯直连健康检查 %s", "通过" if ok else "失败")
            return ok
        except Exception as e:
            logger.warning("腾讯直连健康检查失败: %s", e)
            return False

    # ---------- 实时行情 ----------

    @retry_on_failure()
    def get_realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取实时行情快照（腾讯 qt.gtimg.cn）

        Args:
            symbols: 股票代码列表，如 ['000001', '600519']

        Returns:
            DataFrame，含 name、price、change_pct、volume、amount、
            high、low、open、pre_close、turnover、pe、market_cap 等 50+ 字段
        """
        self.limiter.wait()

        # 构造查询字符串: sh600519,sz000001
        codes = []
        for s in symbols:
            s = str(s).zfill(6)
            prefix = "sh" if s.startswith(("6", "9")) else "sz"
            codes.append(f"{prefix}{s}")

        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        logger.info("腾讯直连实时行情: %d 只", len(symbols))

        r = self._session.get(url, timeout=10)
        r.encoding = "gbk"
        text = r.text

        rows = []
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            # 格式: v_sh600519="1~贵州茅台~600519~..."
            value_str = line.split("=", 1)[1].strip().strip('";')
            fields = value_str.split("~")
            if len(fields) < 40:
                continue

            try:
                rows.append({
                    "symbol": fields[2],
                    "name": fields[1],
                    "price": float(fields[3]) if fields[3] else None,
                    "pre_close": float(fields[4]) if fields[4] else None,
                    "open": float(fields[5]) if fields[5] else None,
                    "volume": float(fields[6]) if fields[6] else 0,  # 手
                    "high": float(fields[33]) if len(fields) > 33 and fields[33] else None,
                    "low": float(fields[34]) if len(fields) > 34 and fields[34] else None,
                    "amount": float(fields[37]) if len(fields) > 37 and fields[37] else 0,  # 万元
                    "change_pct": float(fields[32]) if len(fields) > 32 and fields[32] else None,
                    "turnover": float(fields[38]) if len(fields) > 38 and fields[38] else None,
                    "pe": float(fields[39]) if len(fields) > 39 and fields[39] else None,
                    "market_cap": float(fields[45]) if len(fields) > 45 and fields[45] else None,
                })
            except (ValueError, IndexError) as e:
                logger.debug("腾讯实时行情解析跳过 %s: %s", fields[2] if len(fields) > 2 else "?", e)
                continue

        logger.info("腾讯直连实时行情: %d 条", len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ---------- K 线 ----------

    @retry_on_failure()
    def get_kline(
        self,
        symbol: str,
        freq: str = "day",
        start_date: str = "",
        end_date: str = "",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        获取历史 K 线（腾讯 proxy.finance.qq.com）

        Args:
            symbol: 6 位股票代码，如 '600519'
            freq: 周期，"day"/"week"/"month"
            start_date: 起始日期 YYYY-MM-DD，默认 1 年前
            end_date: 截止日期 YYYY-MM-DD，默认今天
            adjust: 复权方式，"qfq"(前复权)/"hfq"(后复权)/""(不复权)

        Returns:
            DataFrame，标准 OHLCV 格式
        """
        self.limiter.wait()

        symbol = str(symbol).zfill(6)
        prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
        code = f"{prefix}{symbol}"

        today = datetime.now()
        if not end_date:
            end_date = today.strftime("%Y-%m-%d")
        if not start_date:
            start_date = f"{today.year - 1}-01-01"

        year = today.year

        url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
        params = {
            "_var": f"kline_{freq}{adjust}{year}",
            "param": f"{code},{freq},{start_date},{end_date},640,{adjust}",
            "r": str(__import__("random").random()),
        }

        logger.info("腾讯直连 K 线: %s (%s, %s~%s)", symbol, freq, start_date, end_date)

        r = self._session.get(url, params=params, timeout=15)
        text = r.text

        # 返回是 JSONP: kline_dayqfq2026={...}
        # 提取 JSON 部分
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            logger.warning("腾讯 K 线返回格式异常: %s", symbol)
            return pd.DataFrame()

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("腾讯 K 线 JSON 解析失败: %s", symbol)
            return pd.DataFrame()

        # 提取 K 线数据
        klines = None
        if "data" in data and code in data["data"]:
            stock_data = data["data"][code]
            if isinstance(stock_data, dict):
                # key 格式: qfqday / hfqweek / month（adjust在前，freq在后）
                klines = (stock_data.get(f"{adjust}{freq}")
                          or stock_data.get(freq)
                          or stock_data.get(f"{adjust}day"))
            elif isinstance(stock_data, list):
                klines = stock_data

        if not klines:
            logger.warning("腾讯 K 线无数据: %s", symbol)
            return pd.DataFrame()

        rows = []
        for item in klines:
            if len(item) < 6:
                continue
            try:
                rows.append({
                    "date": item[0],
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]) if len(item) > 5 else 0,
                })
            except (ValueError, TypeError):
                continue

        logger.info("腾讯直连 K 线: %s 共 %d 条", symbol, len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()
