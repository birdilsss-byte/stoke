"""
A 股交易日历

提供交易日判断、上一交易日计算等功能。
数据来源：新浪财经交易日历（通过 akshare 获取），首次加载后缓存在内存。
"""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from stoke.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_CACHE: Optional[set] = None
_CALENDAR_LIMITER = RateLimiter(interval=5.0)  # akshare 5 秒限流


def _load_trading_days() -> set:
    """加载交易日历（首次网络请求，后续用内存缓存）"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    try:
        _CALENDAR_LIMITER.wait()
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        _CACHE = set(
            pd.to_datetime(df["trade_date"]).dt.date.tolist()
        )
        logger.info("交易日历加载完成，共 %d 个交易日", len(_CACHE))
    except Exception as e:
        logger.error("交易日历加载失败: %s，降级为周一至周五判断", e)
        _CACHE = set()
    return _CACHE


def is_trading_day(d: Optional[date] = None) -> bool:
    """判断是否为交易日"""
    if d is None:
        d = date.today()

    trading_days = _load_trading_days()
    if trading_days:
        return d in trading_days
    return d.weekday() < 5


def today_str() -> str:
    """返回今天的 YYYYMMDD 字符串（如果是非交易日，返回最近交易日）"""
    d = date.today()
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d.strftime("%Y%m%d")


def prev_trading_day(d: Optional[date] = None) -> date:
    """返回上一个交易日"""
    if d is None:
        d = date.today()
    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d = d - timedelta(days=1)
    return d


def trading_days_between(start: date, end: date) -> list[date]:
    """返回两个日期之间的所有交易日（含起止）"""
    trading_days = _load_trading_days()
    if trading_days:
        return sorted([d for d in trading_days if start <= d <= end])
    result = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            result.append(d)
        d = d + timedelta(days=1)
    return result
