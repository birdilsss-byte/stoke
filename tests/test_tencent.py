"""
乐咕乐股估值数据源测试（legulegu — 纯 requests，零 akshare 依赖）
"""
from stoke.sources.legulegu_source import LeguleguSource

l = LeguleguSource()

# 连通性
assert l.health_check(), "乐咕乐股不可用!"
print("OK 乐咕乐股连通性通过")

# 指数 PE
df = l.get_index_pe("上证50")
assert len(df) > 100, f"上证50 PE 数据异常: {len(df)} 条"
print(f"OK 上证50 PE: {len(df)} 条, 最近 PE={df['滚动市盈率'].iloc[-1]:.2f}")

# 全市场 PB
df = l.get_market_pb()
assert len(df) > 100, f"全市场 PB 数据异常: {len(df)} 条"
print(f"OK 全市场 PB: {len(df)} 条, 最近 PB={df['middlePB'].iloc[-1]:.2f}")
