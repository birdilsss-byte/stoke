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

# akshare 独占、无备份的方法 — 不可用时优雅降级
_AKSHARE_ONLY = {
    "limit_up", "strong_stocks", "limit_down",
    "sector_rank", "market_breadth", "market_volume",
    "northbound_flow", "margin_shanghai", "margin_shenzhen",
    "market_fund_flow", "hot_keywords", "hot_detail",
    "hot_latest", "hot_realtime", "xueqiu_hot",
    "stock_comment_all", "stock_desire", "stock_focus",
    "concepts", "industries", "sector_kline",
    "news", "telegraph", "research", "announcements",
}


def _sina_realtime(symbols: List[str]) -> pd.DataFrame:
    """新浪财经实时行情（hq.sinajs.cn），纯 requests"""
    codes = []
    for s in symbols:
        s = str(s).zfill(6)
        prefix = "sh" if s.startswith(("6", "9")) else "sz"
        codes.append(f"{prefix}{s}")

    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    r = requests.get(url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"})
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
                "symbol": fields[0] or "",
                "name": fields[1] if len(fields) > 1 else "",
                "price": float(fields[3]) if fields[3] else None,
                "change_pct": float(fields[4]) if fields[4] else None,
                "volume": float(fields[8]) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "high": float(fields[5]) if fields[5] else None,
                "low": float(fields[6]) if fields[6] else None,
                "open": float(fields[2]) if fields[2] else None,
            })
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


class FallbackStoke:
    """
    带多源自动备份的 Stoke 包装器

    备份链：
      kline:         mootdx → efinance → baostock → 腾讯直连
      realtime:      mootdx → 腾讯直连 → 新浪直连 → efinance
      stock_list:    mootdx → baostock
      dragon_tiger:  efinance ↔ akshare
      individual_fund_flow: efinance → akshare
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
        """日 K 线：mootdx → efinance → baostock → 腾讯直连"""
        if frequency != 9:
            return self._s.kline(symbol, frequency, start, offset)

        return self._fallback_call("kline", [
            lambda: self._s.kline(symbol, frequency, start, offset),
            lambda: self._s.kline_efinance(symbol),
            lambda: self._raw.baostock.get_kline(
                f"sh.{symbol}" if symbol.startswith("6") else f"sz.{symbol}",
                frequency="d",
            ),
            lambda: self._raw.tencent_direct.get_kline(symbol),
        ])

    # ==================== 实时行情（4 级备份） ====================

    def realtime(self, symbols: List[str]) -> pd.DataFrame:
        """实时行情：mootdx → 腾讯直连 → 新浪直连 → efinance"""
        return self._fallback_call("realtime", [
            lambda: self._s.realtime(symbols),
            lambda: self._raw.tencent_direct.get_realtime(symbols),
            lambda: _sina_realtime(symbols),
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
            lambda: self._s.dragon_tiger(),
            lambda: self._raw.akshare.get_dragon_tiger(),
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
        symbol_map = {"上证50": "sh.600000", "沪深300": "sh.600000", "中证500": "sz.000001"}
        sym = symbol_map.get(index_name, "sh.600000")

        return self._fallback_call("index_pe", [
            lambda: self._s.index_pe(index_name),
            lambda: self._raw.baostock.get_kline_with_valuation(sym),
        ])

    # ==================== 板块成分股（新增备份） ====================

    def sector_members(self, sector_name: str) -> pd.DataFrame:
        """板块成分股：mootdx → efinance"""
        return self._fallback_call("sector_members", [
            lambda: self._s.sector_members(sector_name),
            lambda: self._raw.efinance.get_realtime_all(),
        ])

    # ==================== akshare 独占方法：优雅降级 ====================

    def __getattr__(self, name):
        """覆盖 + 透传：akshare 独占方法加优雅降级，其余直通 StokeCached"""
        if name.startswith("_"):
            raise AttributeError(name)

        method = getattr(self._s, name)
        if name in _AKSHARE_ONLY:
            def _guarded(*args, _m=name, _fn=method, **kwargs):
                if not akshare_ok():
                    logger.warning("%s: akshare 不可用，返回空数据（优雅降级）", _m)
                    return pd.DataFrame()
                return _fn(*args, **kwargs)
            return _guarded
        return method
