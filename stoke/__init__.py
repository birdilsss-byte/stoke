"""
Stoke — A股量化投研数据层

5 大源，各司其职，零 API Key：
  mootdx (TCP)     — K线/实时行情/指数/板块，不限速
  akshare (HTTP)   — 新闻/研报/涨停/情绪/资金流/行业，5s限流
  baostock (HTTP)  — 复权K线/行业分类，1s限流
  efinance (HTTP)  — 极速K线/龙虎榜/股东数据，零限制
  tencent (HTTP)   — PE/PB估值，3s限流

用法::
    from stoke import Stoke          # 默认带缓存
    s = Stoke()
    df = s.kline("000001")

    from stoke.client import Stoke as StokeRaw  # 裸版，无缓存
    raw = StokeRaw()
"""

from stoke.client_cached import StokeCached as Stoke
from stoke.fallback import FallbackStoke

__version__ = "1.3.0"
__all__ = ["Stoke", "FallbackStoke"]

