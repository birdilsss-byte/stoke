"""
腾讯财经直连数据源 — 纯 requests，零 akshare 依赖

端点：
  - qt.gtimg.cn             实时行情（50+ 字段，毫秒级响应）
  - qt.gtimg.cn/q=s_        简要信息
  - qt.gtimg.cn/q=s_pk      盘口大单分析
  - proxy.finance.qq.com    K 线（日/周/月，前/后复权）
  - proxy.finance.qq.com    分钟 K 线（m5/m15/m30/m60）
  - web.ifzq.gtimg.cn       分时数据（日内 line + mline）

免费、零注册、零 API Key。
"""

import logging
import json
import random
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
    """腾讯财经直连数据源 — 实时行情 + K 线 + 分钟K线 + 分时 + 跨市场"""

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

    # ==================== 公用解析器 ====================

    @staticmethod
    def _parse_realtime_response(text: str) -> pd.DataFrame:
        """
        从 qt.gtimg.cn 的 ~ 分隔响应中解析实时行情

        Args:
            text: qt.gtimg.cn 返回的原始文本（GBK 编码已解码）

        Returns:
            DataFrame，含 name、price、change_pct、volume、amount、
            high、low、open、pre_close、turnover、pe、market_cap 等 50+ 字段
        """
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
                logger.debug("腾讯实时行情解析跳过 %s: %s",
                             fields[2] if len(fields) > 2 else "?", e)
                continue

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================== 实时行情（A 股） ====================

    @retry_on_failure()
    def get_realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取 A 股实时行情快照（腾讯 qt.gtimg.cn）

        自动识别沪/深市场前缀：
          - 6 或 9 开头 → 沪市（sh）
          - 其余 → 深市（sz）

        如需港股/美股/指数，请用 get_market_realtime()。

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
        logger.info("腾讯直连 A 股实时行情: %d 只", len(symbols))

        r = self._session.get(url, timeout=10)
        r.encoding = "gbk"
        df = self._parse_realtime_response(r.text)
        logger.info("腾讯直连 A 股实时行情: %d 条", len(df))
        return df

    # ==================== 跨市场实时行情 ====================

    @retry_on_failure()
    def get_market_realtime(self, codes: List[str]) -> pd.DataFrame:
        """
        获取跨市场实时行情（腾讯 qt.gtimg.cn）

        与 get_realtime() 不同，此方法接受已包含市场前缀的完整代码，
        如 'sh000001'、'hk00700'、'usAAPL'、'sz159915'、'sh510050'。
        不自动添加任何前缀。

        Args:
            codes: 已包含市场前缀的代码列表，如 ['sh000001', 'hk00700', 'usAAPL']

        Returns:
            DataFrame，同 get_realtime() 格式
        """
        self.limiter.wait()

        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        logger.info("腾讯直连跨市场行情: %d 只", len(codes))

        r = self._session.get(url, timeout=10)
        r.encoding = "gbk"
        df = self._parse_realtime_response(r.text)
        logger.info("腾讯直连跨市场行情: %d 条", len(df))
        return df

    # ==================== 简要信息 ====================

    @retry_on_failure()
    def get_brief_info(self, codes: List[str]) -> pd.DataFrame:
        """
        获取简要行情信息（腾讯 qt.gtimg.cn q=s_ 前缀）

        比 get_realtime() 轻量，仅含核心字段：
        name、price、change、change_pct、volume、amount、market_cap。

        Args:
            codes: 已包含市场前缀的代码列表，如 ['sh600519', 'hk00700']

        Returns:
            DataFrame，含 symbol、name、price、change、change_pct、
            volume(手)、amount(万元)、market_cap(亿元)
        """
        self.limiter.wait()

        # 加 s_ 前缀: s_sh600519, s_hk00700
        prefixed = ",".join(f"s_{c}" for c in codes)
        url = f"http://qt.gtimg.cn/q={prefixed}"
        logger.info("腾讯直连简要信息: %d 只", len(codes))

        r = self._session.get(url, timeout=10)
        r.encoding = "gbk"
        text = r.text

        rows = []
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            value_str = line.split("=", 1)[1].strip().strip('";')
            fields = value_str.split("~")
            if len(fields) < 10:
                continue
            try:
                rows.append({
                    "symbol": fields[2],                    # 代码
                    "name": fields[1],                      # 名称
                    "price": float(fields[3]) if fields[3] else None,
                    "change": float(fields[4]) if fields[4] else None,      # 涨跌额
                    "change_pct": float(fields[5]) if fields[5] else None,  # 涨跌幅
                    "volume": float(fields[6]) if fields[6] else 0,         # 成交量(手)
                    "amount": float(fields[7]) if fields[7] else 0,         # 成交额(万元)
                    "market_cap": float(fields[9]) if len(fields) > 9 and fields[9] else None,
                })
            except (ValueError, IndexError):
                continue

        logger.info("腾讯直连简要信息: %d 条", len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================== 盘口大单分析 ====================

    @retry_on_failure()
    def get_tick_analysis(self, symbol: str) -> pd.DataFrame:
        """
        获取逐笔成交大单/小单分析（腾讯 qt.gtimg.cn q=s_pk 前缀）

        反映主力 vs 散户的博弈状态。

        Args:
            symbol: 已包含市场前缀的代码，如 'sh600519'

        Returns:
            DataFrame，含 4 字段：
            buy_big_ratio(买盘大单比率)、buy_small_ratio(买盘小单比率)、
            sell_big_ratio(卖盘大单比率)、sell_small_ratio(卖盘小单比率)
        """
        self.limiter.wait()

        url = f"http://qt.gtimg.cn/q=s_pk{symbol}"
        logger.info("腾讯直连逐笔分析: %s", symbol)

        r = self._session.get(url, timeout=10)
        r.encoding = "gbk"
        text = r.text

        rows = []
        for line in text.strip().split("\n"):
            if not line.strip() or "=" not in line:
                continue
            value_str = line.split("=", 1)[1].strip().strip('";')
            fields = value_str.split("~")
            if len(fields) < 4:
                continue
            try:
                rows.append({
                    "buy_big_ratio": float(fields[0]) if fields[0] else None,
                    "buy_small_ratio": float(fields[1]) if fields[1] else None,
                    "sell_big_ratio": float(fields[2]) if fields[2] else None,
                    "sell_small_ratio": float(fields[3]) if fields[3] else None,
                })
            except (ValueError, IndexError):
                continue

        logger.info("腾讯直连逐笔分析: %s 完成", symbol)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================== 分钟 K 线 ====================

    @retry_on_failure()
    def get_minute_kline(
        self,
        symbol: str,
        freq: str = "m5",
        count: int = 240,
    ) -> pd.DataFrame:
        """
        获取分钟级 K 线（腾讯 proxy.finance.qq.com/mkline）

        支持 5/15/30/60 分钟周期，最多返回 240 条记录。

        Args:
            symbol: 已包含市场前缀的代码，如 'sh600519'
            freq: 分钟周期，"m5"/"m15"/"m30"/"m60"
            count: 记录条数，默认 240

        Returns:
            DataFrame，含 datetime(YYYYMMDDHHMM)、open、close、high、low、volume
        """
        self.limiter.wait()

        url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/kline/mkline"
        params = {
            "param": f"{symbol},{freq},,{count}",
            "r": str(random.random()),
        }

        logger.info("腾讯直连分钟 K 线: %s (%s, %d 条)", symbol, freq, count)

        r = self._session.get(url, params=params, timeout=15)

        # JSONP 解析: 提取 {...} 部分
        match = re.search(r'\{.*\}', r.text, re.DOTALL)
        if not match:
            logger.warning("腾讯分钟 K 线返回格式异常: %s", symbol)
            return pd.DataFrame()

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("腾讯分钟 K 线 JSON 解析失败: %s", symbol)
            return pd.DataFrame()

        # 提取分钟 K 线
        klines = None
        stock_data = data.get("data", {})
        if isinstance(stock_data, dict):
            inner = stock_data.get(symbol)
            if isinstance(inner, dict):
                klines = inner.get(freq)  # freq="m5"/"m15"/"m30"/"m60"

        if not klines:
            logger.warning("腾讯分钟 K 线无数据: %s (%s)", symbol, freq)
            return pd.DataFrame()

        rows = []
        for item in klines:
            if len(item) < 6:
                continue
            try:
                rows.append({
                    "datetime": str(item[0]),   # YYYYMMDDHHMM
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]),
                })
            except (ValueError, TypeError):
                continue

        logger.info("腾讯直连分钟 K 线: %s 共 %d 条", symbol, len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================== 分时数据 ====================

    def _fetch_intraday(self, symbol: str) -> dict:
        """内部方法：通用分时数据请求，返回原始 JSON"""
        url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
        params = {"code": symbol}
        r = self._session.get(url, params=params, timeout=15)
        return r.json()

    @retry_on_failure()
    def get_intraday_line(self, symbol: str) -> pd.DataFrame:
        """
        获取当日分时线（腾讯 web.ifzq.gtimg.cn/minute/query）

        Args:
            symbol: 已包含市场前缀的代码，如 'sh600519'

        Returns:
            DataFrame，含 time、price、avg_price、volume(手)、amount(万元)
        """
        self.limiter.wait()
        logger.info("腾讯直连分时线: %s", symbol)

        data = self._fetch_intraday(symbol)
        line_data = data.get("data", {}).get("line", [])

        rows = []
        for item in line_data:
            if len(item) < 5:
                continue
            try:
                rows.append({
                    "time": str(item[0]),
                    "price": float(item[1]),
                    "avg_price": float(item[2]),
                    "volume": float(item[3]),
                    "amount": float(item[4]),
                })
            except (ValueError, TypeError, IndexError):
                continue

        logger.info("腾讯直连分时线: %s %d 条", symbol, len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @retry_on_failure()
    def get_intraday_mline(self, symbol: str) -> pd.DataFrame:
        """
        获取当日分钟级 K 线（腾讯 web.ifzq.gtimg.cn/minute/query）

        Args:
            symbol: 已包含市场前缀的代码，如 'sh600519'

        Returns:
            DataFrame，含 time、open、close、high、low、volume(手)、amount(万元)
        """
        self.limiter.wait()
        logger.info("腾讯直连分时分钟K线: %s", symbol)

        data = self._fetch_intraday(symbol)
        mline_data = data.get("data", {}).get("mline", [])

        rows = []
        for item in mline_data:
            if len(item) < 7:
                continue
            try:
                rows.append({
                    "time": str(item[0]),
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]),
                    "amount": float(item[6]),
                })
            except (ValueError, TypeError, IndexError):
                continue

        logger.info("腾讯直连分时分钟K线: %s %d 条", symbol, len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    # ==================== 复权 K 线 ====================

    @retry_on_failure()
    def get_fqkline(
        self,
        symbol: str,
        freq: str = "day",
        start_date: str = "",
        end_date: str = "",
        adjust: str = "hfq",
    ) -> pd.DataFrame:
        """
        获取复权 K 线（腾讯 ifzq.gtimg.cn/fqkline）

        与 get_kline() 的不同之处：
          - 使用独立端点 ifzq.gtimg.cn/appstock/app/fqkline/get
          - 支持 hfq（后复权），适用于需要完整复权历史的场景

        Args:
            symbol: 已包含市场前缀的代码，如 'sh600519'
            freq: 周期，"day"/"week"/"month"
            start_date: 起始日期 YYYY-MM-DD，默认 1 年前
            end_date: 截止日期 YYYY-MM-DD，默认今天
            adjust: 复权方式，"qfq"(前复权)/"hfq"(后复权)

        Returns:
            DataFrame，标准 OHLCV 格式，含 date、open、close、high、low、volume
        """
        self.limiter.wait()

        today = datetime.now()
        if not end_date:
            end_date = today.strftime("%Y-%m-%d")
        if not start_date:
            start_date = f"{today.year - 1}-01-01"

        url = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{symbol},{freq},{start_date},{end_date},640,{adjust}",
            "r": str(random.random()),
        }

        logger.info("腾讯直连复权 K 线: %s (%s, %s~%s, %s)",
                     symbol, freq, start_date, end_date, adjust)

        r = self._session.get(url, params=params, timeout=15)
        text = r.text

        # JSONP 提取
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            logger.warning("腾讯复权 K 线返回格式异常: %s", symbol)
            return pd.DataFrame()

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("腾讯复权 K 线 JSON 解析失败: %s", symbol)
            return pd.DataFrame()

        # 提取 K 线数据
        klines = None
        if "data" in data and symbol in data["data"]:
            stock_data = data["data"][symbol]
            if isinstance(stock_data, dict):
                klines = (stock_data.get(f"{adjust}{freq}")
                          or stock_data.get(freq)
                          or stock_data.get(f"{adjust}day"))

        if not klines:
            logger.warning("腾讯复权 K 线无数据: %s", symbol)
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

        logger.info("腾讯直连复权 K 线: %s 共 %d 条", symbol, len(rows))
        return pd.DataFrame(rows) if rows else pd.DataFrame()
