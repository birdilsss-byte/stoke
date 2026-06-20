"""
数据源适配层

每个 Source 类：
  - 构造函数接受 rate_limiter 参数（可选，默认启用）
  - 实现 health_check() -> bool
  - 返回 pandas DataFrame 或 list[dict]
"""

from stoke.sources.mootdx_source import MootdxSource
from stoke.sources.akshare_source import AKShareSource
from stoke.sources.legulegu_source import LeguleguSource
from stoke.sources.baostock_source import BaostockSource
from stoke.sources.efinance_source import EFinanceSource
from stoke.sources.tencent_direct_source import TencentDirectSource
from stoke.sources.eastmoney_source import EastMoneySource
from stoke.sources.ths_source import ThsSource
from stoke.sources.datacenter_source import DatacenterSource
from stoke.sources.cninfo_source import CninfoSource
__all__ = [
    "MootdxSource",
    "AKShareSource",
    "LeguleguSource",
    "BaostockSource",
    "EFinanceSource",
    "TencentDirectSource",
    "EastMoneySource",
    "ThsSource",
    "DatacenterSource",
    "CninfoSource",
]
