"""
FallbackStoke — 带多源自动备份的 Stoke 包装器

当主数据源不可用时，自动按优先级尝试备用源。
akshare 独占方法在 akshare 不可用时优雅降级（空 DataFrame + warning）。

用法::
    from stoke.fallback import FallbackStoke
    s = FallbackStoke()
    df = s.kline("000001")    # mootdx → efinance → baostock → 腾讯直连
"""

import logging
from typing import Optional, List

import pandas as pd
import requests

from stoke.client_cached import StokeCached
from stoke.exceptions import DataEmptyError
from stoke.probe import akshare_ok

logger = logging.getLogger(__name__)


def _sina_realtime(symbols: List[str]) -> pd.DataFrame:
    """
    新浪财经实时行情（hq.sinajs.cn），纯 requests，零依赖。

    Args:
        symbols: 股票代码列表，如 ['000001', '600519']
    """
    codes = []
    for s in symbols:
        s = str(s).zfill(6)
        prefix = "sh" if s.startswith(("6", "9")) else "sz"
        codes.append(f"{prefix}{s}")

    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    r = requests.get(
        url, timeout=10,
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    r.encoding = "gbk"

    rows = []
    for line in r.text.strip().split("\n"):
        if "=" not in line:
            continue
        try:
            value_str = line.split("=", 1)[1].strip().strip('";')
            if not value_str:
                continue
            fields = value_str.split(",")
            if len(fields) < 30:
                continue
            rows.append({
                "symbol": fields[0] if fields[0] else "",
                "name": fields[1] if len(fields) > 1 else "",
                "price": float(fields[3]) if fields[3] else None,
                "change_pct": float(fields[4]) if fields[4] else None,
                "volume": float(fields[8]) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "high": float(fields[5]) if fields[5] else None,
                "low": float(fields[6]) if fields[6] else None,
                "open": float(fields[2]) if fields[2] else None,
                "pre_close": float(fields[3]) if fields[3] else None,
            })
        except (ValueError, IndexError) as e:
            logger.debug("新浪实时行情解析跳过: %s", e)
            continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _graceful_empty(name: str) -> pd.DataFrame:
    """
    akshare 不可用时的优雅降级：返回空 DataFrame + warning。
    不抛异常，不阻塞主流程。
    """
    logger.warning("%s: akshare 不可用，返回空数据（优雅降级）", name)
    return pd.DataFrame()


class FallbackStoke:
    """
    带多源自动备份的 Stoke 包装器

    备份链：
      kline:         mootdx → efinance → baostock → 腾讯直连
      realtime:      mootdx → 腾讯直连 → 新浪直连 → efinance
      stock_list:    mootdx → baostock
      dragon_tiger:  efinance ↔ akshare
      capital_flow:  efinance → akshare
      index_pe:      legulegu → baostock K线估值
      sector_members:mootdx → efinance
      akshare独占:   优雅降级（空DataFrame + warning）
    """

    def __init__(self, stoke: Optional[StokeCached] = None, probe: bool = True):
        self._s = stoke or StokeCached()
        self._raw = self._s.raw
        if probe:
            try:
                from stoke.probe import probe_sources
                probe_sources(self._raw)
            except Exception as e:
                logger.debug("自动探路跳过: %s", e)
        logger.info("FallbackStoke 初始化完成（7 个方法带多级备份）")

    def _fallback_call(self, name: str, fns: list) -> pd.DataFrame:
        """按优先级尝试多个数据源，全部失败时抛出 DataEmptyError"""
        last_exc = None
        for level, fn in enumerate(fns):
            try:
                result = fn()
                if isinstance(result, pd.DataFrame) and not result.empty:
                    if level > 0:
                        logger.info("%s: 主源不可用，已从第 %d 级备用源返回", name, level)
                    return result
                if isinstance(result, pd.DataFrame):
                    logger.warning("%s: 第 %d 级源返回空数据", name, level)
            except Exception as e:
                last_exc = e
                logger.warning("%s: 第 %d 级源失败 (%s: %s)", name, level, type(e).__name__, e)
        raise DataEmptyError(f"{name}: 所有数据源均不可用") from last_exc

    # ==================== kline（4 级备份） ====================

    def kline(self, symbol: str, frequency: int = 9,
              start: int = 0, offset: int = 800) -> pd.DataFrame:
        """
        日 K 线：mootdx → efinance → baostock → 腾讯直连

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
            lambda: self._raw.baostock.get_kline(
                f"sh.{symbol}" if symbol.startswith("6") else f"sz.{symbol}",
                frequency="d",
            ),
            # Level 3: 腾讯直连 K 线
            lambda: self._raw.tencent_direct.get_kline(symbol),
        ])

    # ==================== 实时行情（4 级备份） ====================

    def realtime(self, symbols: List[str]) -> pd.DataFrame:
        """
        实时行情：mootdx → 腾讯直连 → 新浪直连 → efinance
        """
        return self._fallback_call("realtime", [
            # Level 0: mootdx（TCP，含 5 档盘口）
            lambda: self._s.realtime(symbols),
            # Level 1: 腾讯直连 qt.gtimg.cn（毫秒级）
            lambda: self._raw.tencent_direct.get_realtime(symbols),
            # Level 2: 新浪直连 hq.sinajs.cn
            lambda: _sina_realtime(symbols),
            # Level 3: efinance（15s 延迟）
            lambda: self._raw.efinance.get_realtime(symbols),
        ])

    # ==================== 股票列表（2 级备份） ====================

    def stock_list(self) -> pd.DataFrame:
        """全市场股票列表：mootdx → baostock"""
        return self._fallback_call("stock_list", [
            lambda: self._s.stock_list(),
            lambda: self._s.all_stock(),
        ])

    # ==================== 龙虎榜（双向备份） ====================

    def dragon_tiger(self) -> pd.DataFrame:
        """龙虎榜：efinance ↔ akshare 双向备份"""
        return self._fallback_call("dragon_tiger", [
            lambda: self._s.dragon_tiger(),  # efinance（主源，更详细）
            lambda: self._raw.akshare.get_dragon_tiger(),  # akshare 备用
        ])

    # ==================== 资金流（新增备份） ====================

    def individual_fund_flow(self, symbol: str) -> pd.DataFrame:
        """个股资金流：efinance → akshare"""
        return self._fallback_call("individual_fund_flow", [
            lambda: self._raw.efinance.get_capital_flow(symbol),
            lambda: self._raw.akshare.get_individual_fund_flow(symbol),
        ])

    # ==================== 指数 PE（新增备份） ====================

    def index_pe(self, index_name: str = "上证50") -> pd.DataFrame:
        """指数 PE：legulegu → baostock K 线估值"""
        def _bs_pe():
            """从 baostock K 线中提取 PE 估值"""
            import baostock as bs
            # 指数成分股取上证50的第一只来代表（近似方案）
            symbol_map = {
                "上证50": "sh.600000",
                "沪深300": "sh.600000",
                "中证500": "sz.000001",
            }
            sym = symbol_map.get(index_name, "sh.600000")
            df = self._raw.baostock.get_kline_with_valuation(sym)
            if not df.empty and "peTTM" in df.columns:
                df = df.rename(columns={"peTTM": "滚动市盈率"})
            return df

        return self._fallback_call("index_pe", [
            lambda: self._s.index_pe(index_name),  # legulegu（主源）
            _bs_pe,  # baostock 估值字段备用
        ])

    # ==================== 板块成分股（新增备份） ====================

    def sector_members(self, sector_name: str) -> pd.DataFrame:
        """板块成分股：mootdx → efinance"""
        return self._fallback_call("sector_members", [
            lambda: self._s.sector_members(sector_name),
            lambda: self._raw.efinance.get_realtime_all(),  # 全市场快照（近似）
        ])

    # ==================== akshare 独占方法：优雅降级 ====================

    def limit_up(self, date=None):
        if not akshare_ok():
            return _graceful_empty("limit_up")
        return self._s.limit_up(date)

    def strong_stocks(self, date=None):
        if not akshare_ok():
            return _graceful_empty("strong_stocks")
        return self._s.strong_stocks(date)

    def limit_down(self, date=None):
        if not akshare_ok():
            return _graceful_empty("limit_down")
        return self._s.limit_down(date)

    def sector_rank(self):
        if not akshare_ok():
            return _graceful_empty("sector_rank")
        return self._s.sector_rank()

    def market_breadth(self):
        if not akshare_ok():
            return _graceful_empty("market_breadth")
        return self._s.market_breadth()

    def market_volume(self):
        if not akshare_ok():
            return _graceful_empty("market_volume")
        return self._s.market_volume()

    def northbound_flow(self):
        if not akshare_ok():
            return _graceful_empty("northbound_flow")
        return self._s.northbound_flow()

    def margin_shanghai(self):
        if not akshare_ok():
            return _graceful_empty("margin_shanghai")
        return self._s.margin_shanghai()

    def margin_shenzhen(self):
        if not akshare_ok():
            return _graceful_empty("margin_shenzhen")
        return self._s.margin_shenzhen()

    def market_fund_flow(self):
        if not akshare_ok():
            return _graceful_empty("market_fund_flow")
        return self._s.market_fund_flow()

    def hot_keywords(self):
        if not akshare_ok():
            return _graceful_empty("hot_keywords")
        return self._s.hot_keywords()

    def hot_detail(self, symbol):
        if not akshare_ok():
            return _graceful_empty("hot_detail")
        return self._s.hot_detail(symbol)

    def hot_latest(self, symbol):
        if not akshare_ok():
            return _graceful_empty("hot_latest")
        return self._s.hot_latest(symbol)

    def hot_realtime(self, symbol):
        if not akshare_ok():
            return _graceful_empty("hot_realtime")
        return self._s.hot_realtime(symbol)

    def xueqiu_hot(self, mode="最热门"):
        if not akshare_ok():
            return _graceful_empty("xueqiu_hot")
        return self._s.xueqiu_hot(mode)

    def stock_comment_all(self):
        if not akshare_ok():
            return _graceful_empty("stock_comment_all")
        return self._s.stock_comment_all()

    def stock_desire(self, symbol):
        if not akshare_ok():
            return _graceful_empty("stock_desire")
        return self._s.stock_desire(symbol)

    def stock_focus(self, symbol):
        if not akshare_ok():
            return _graceful_empty("stock_focus")
        return self._s.stock_focus(symbol)

    def concepts(self):
        if not akshare_ok():
            return _graceful_empty("concepts")
        return self._s.concepts()

    def industries(self):
        if not akshare_ok():
            return _graceful_empty("industries")
        return self._s.industries()

    def sector_kline(self, symbol="银行", start_date="20250101", end_date=""):
        if not akshare_ok():
            return _graceful_empty("sector_kline")
        return self._s.sector_kline(symbol, start_date, end_date)

    def news(self, symbol):
        if not akshare_ok():
            return _graceful_empty("news")
        return self._s.news(symbol)

    def telegraph(self):
        if not akshare_ok():
            return _graceful_empty("telegraph")
        return self._s.telegraph()

    def research(self, symbol):
        if not akshare_ok():
            return _graceful_empty("research")
        return self._s.research(symbol)

    def announcements(self, symbol):
        if not akshare_ok():
            return _graceful_empty("announcements")
        return self._s.announcements(symbol)

    # ==================== 透传 StokeCached ====================

    def __getattr__(self, name):
        """未覆盖的方法直接透传到 StokeCached"""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._s, name)
